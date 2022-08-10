import argparse
import io
import sys
from pathlib import Path
from bs4 import BeautifulSoup
from functools import reduce
from bs4.formatter import HTMLFormatter
import re
from googletrans import Translator
import json
import translators as ts
import datetime
import csv

import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from apiclient.http import MediaFileUpload
from googleapiclient.http import MediaIoBaseDownload
import pandas as pd

SCOPES = ['https://www.googleapis.com/auth/drive']

replacements = ['Us2Button', 'cdkDropListGroup',
                '[matTooltipClass]', '#relatedFindingRow', '[matTooltipPosition]']
#  these can only replace after the first round else it causes half lowercase statement like cdkDropListdropped
secondary_replacements = ['cdkDrag', 'cdkDropList', 'ngModel', 'matInput', 'matSort',
                          'matRipple', 'matTableExporter', 'matSuffix', 'matTooltipClass', 'showFirstLastButtons', 'matSuffix', 'matTooltipPosition']
remove_tags = [r'</img>', r'=""']
langs = [
    'en',
    'fr',
    'nl',
    'es',
    'zh-TW',
    'zh-CN',
    'pt',
    'ja',
    'ms',
    'de',
    'ar',
    'da',
    'it',
    'ko',
    'no',
    'sv',
    'th',
    'vi']

def convert_tag(path: Path, tag):
    mods = {}
    for attr in tag.attrs.keys():
        if attr.find('i18n') != -1:
            # Change to upper and dash become underscore,
            loc = ''.join(map(str.capitalize, path.stem.split(".")[:-1]))
            loc = loc.replace('-', '_')
            # if id = None, like for TOS, need to replace it with something
            id = tag[attr].split('@')[-1]
            if attr.find('-') != -1:
                type_token = attr.split('-')[-1]
                try:
                    val = tag[type_token]
                # broken translation need to clean up
                except KeyError:
                    if f"[{attr}]" in tag.attrs.keys():
                        mods[attr] = {}
                    continue
                if id == "":
                    val_list = val.split(' ')
                    if len(val_list) > 5:
                        id = ' '.join(val_list[:5])
                    else:
                        id = val
                mods[attr] = {'type': "[%s]" % (
                    type_token), 'val': "'%s.%s' | translate : {default: '%s'}" % (loc.upper(), id, val)}
            else:
                val = reduce(lambda x, y: x + str(y), tag.contents)
                val = str(val).strip()
                if id == "":
                    val_list = val.split(' ')
                    if len(val_list) > 5:
                        id = ' '.join(val_list[:5])
                    else:
                        id = val
                tag.string = "{{ '%s.%s' | translate : {default: '%s'} }}" % (
                    loc.upper(), id, val)
                mods[attr] = {}
    for k, v in mods.items():
        del tag[k]
        if len(v) > 0:
            tag[v['type']] = v['val']
            del tag[k.replace('i18n-', '')]
    return mods

# use regex since parser made all lowercase
# replace lowercase attributes with original attributes
# also need to remove =""
def replace_attributes(path: Path, html):
    with open(path) as f:
        s = f.read()
        result = replacements
        for v in re.findall(r'[#*]\S+', s):
            if '=' in v:
                continue
            if '>' in v:
                ind = v.index('>')
                result.append(v[:ind])
            else:
                result.append(v)
        for v in re.findall(r'\S+(?=\S*=[^/])', s):
            if v not in result:
                result.append(v)
        for value in result:
            html = html.replace(value.lower(), value)
        # secondary replacements
        for value in secondary_replacements:
            html = html.replace(value.lower(), value)
        for reg in remove_tags:
            html = re.sub(reg, '', html)
        return html


def write_html(path, soup):
    formatter = HTMLFormatter(indent=4)
    html = soup.prettify(formatter=formatter)
    formatted_html = replace_attributes(path, html)
    with open('output.html', "wt") as file:
        file.write(formatted_html)


#  convert i18n tags into dynamic terms in html files
def convert_file(path: Path):
    paths = [path] if path.is_file() else list(path.rglob('*.html'))
    for html_path in paths:
        soup = BeautifulSoup(open(html_path), 'html.parser')
        tags = soup.findAll(lambda tag: any(
            e.find('i18n') != -1 for e in tag.attrs.keys()))
        mods = {}
        for tag in tags:
            mods = convert_tag(html_path, tag)
        # if there's no change, don't write anything
        if len(mods):
            write_html(html_path, soup)


# add back spacking base on original terms
def format_spacing(term, trans):
    if term[0] == ' ':
        if trans[0] != ' ':
            trans = ' ' + trans
    if term[-1] == ' ':
        if trans[-1] != ' ':
            trans += ' '
    return trans


# load manual translation back into json
def load_manual_translation():
    untranslated = {}
    with open('./assets/untranslated.json') as untrans_file:
        untranslated = json.load(untrans_file)
    for lang in untranslated.keys():
        current = {}
        with open(f'./converted/{lang}.json') as lang_file:
            current = json.load(lang_file)
        terms = untranslated[lang].keys()
        for t in terms:
            try:
                val = ts.bing(t, from_language='en', to_language=lang)
                for loc in untranslated[lang][t]:
                    current[loc][t] = val
            except Exception as e:
                print(e)
        with open(f'./converted/{lang}.json', 'w') as output:
            json.dump(current, output, ensure_ascii=False,
                      indent=4, sort_keys=True)


def translate_bing(val, lang):
    if lang == 'zh-TW':
        lang = 'zh-Hant'
    if lang == 'zh':
        lang = 'zh-Hans'
    return ts.bing(val, from_language='en', to_language=lang)


# compared json to en.json to find terms to translate and add
def translate_files():
    translator = Translator()
    result = {}
    untranslated = {}
    for lang in langs:
        try:
            with open(f'./converted/{lang}.json', encoding='utf-8') as lang_file:
                result[lang] = json.load(lang_file)
        except Exception as e:
            result[lang] = {}
    with open(f'./converted/en.json', encoding='utf-8') as lang_file:
        original = json.load(lang_file)
    for lang in langs:
        for key, terms in original.items():
            for id, val in terms.items():
                if key not in result[lang].keys():
                    result[lang][key] = {}
                if id not in result[lang][key].keys():
                    try:
                        trans_term = translator.translate(val, dest=str(lang))
                        result[lang][key][id] = format_spacing(
                            val, trans_term.text)
                    except Exception as e:
                        try:
                            lang_tag = lang.replace('-', '_')
                            trans_term = translate_bing(val, lang_tag)
                            result[lang][key][id] = format_spacing(
                                val, trans_term)
                        except Exception as e:
                            print(e)
                            # add translation that can't work on google trans API
                            if lang not in untranslated.keys():
                                untranslated[lang] = {}
                            if val not in untranslated[lang].keys():
                                untranslated[lang][val] = [key + '.' + id]
                            else:
                                untranslated[lang][val].append(key + '.' + id)
        # save all translated
        with open(f'./converted/{lang}.json', 'w', encoding='utf-8') as output:
            json.dump(result[lang], output, ensure_ascii=False,
                      indent=4, sort_keys=True)
    with open('./assets/untranslated.json', 'w', encoding='utf-8') as output:
        json.dump(untranslated, output, ensure_ascii=False,
                  indent=4, sort_keys=True)


# remove translation terms across json files
# terms is a list of paired values: [[location, id]]
def remove_translation(terms):
    result = {}
    for lang in langs:
        try:
            with open(f'./converted/{lang}.json') as lang_file:
                result[lang] = json.load(lang_file)
        except Exception as _:
            result[lang] = {}
        for term in terms:
            [location, id] = term
            if location in result.keys() and id in result[location].keys():
                del result[location][id]
            else:
                print(f'Key does not exist: {location} {id}')
        # save all translated
        with open(f'./converted/{lang}.json', 'w') as output:
            json.dump(result[lang], output, ensure_ascii=False,
                    indent=4, sort_keys=True)


#  convert xlf files into json as well as replace i18n ids
def convert_xlf_to_json(path: Path):
    paths = [path] if path.is_file() else list(path.glob('*.xlf'))
    for html_path in paths:
        lang = html_path.stem.split('.')[0]
        soup = BeautifulSoup(open(html_path), 'lxml')
        trans_units = soup.findAll('trans-unit')
        # load current terms
        try:
            with open(f'./converted/{lang}.json') as lang_file:
                result = json.load(lang_file)
        except Exception as e:
            result = {}
        for unit in trans_units:
            id = str(unit.attrs['id'])
            for c in unit.contents:
                if c.name == 'target':
                    val = str(reduce(lambda x, y: x + str(y), c.contents))
                if c.name == 'context-group':
                    for inner_c in c.contents:
                        if hasattr(inner_c, 'context-type') and inner_c.attrs['context-type'] == 'sourcefile':
                            locs = filter(lambda x: x != 'component', reduce(
                                lambda x, y: x + str(y), inner_c.contents).split('/')[-1].split('.')[:-1])
                            loc = '.'.join(locs).upper()
                            if loc not in result.keys():
                                result[loc] = {}
                            if val not in result[loc].values():
                                result[loc][id] = val
        i18n_id = load_i18n_id()
        replace_i18n_id(i18n_id, result, lang)


# extract from en.json the id to create readable key
def extract_i18n_id():
    i18n_id = {}
    with open(f'./converted/en.json') as lang_file:
        original = json.load(lang_file)
    for _, terms in original.items():
        for id, val in terms.items():
            # identify i18n uuid
            if len(id.split(' ')) == 1:
                if len(id) == 40:
                    new_id = ''
                    val_list = val.split(' ')
                    if len(val_list) > 5:
                        new_id = ' '.join(val_list[:5])
                    else:
                        new_id = val
                    i18n_id[id] = new_id
    with open(f'./assets/i18n_id.json', 'w') as output:
        json.dump(i18n_id, output, ensure_ascii=False,
                  indent=4, sort_keys=True)
    return i18n_id


def load_i18n_id():
    i18n_id = {}
    with open(f'./assets/i18n_id.json') as i18n_file:
        i18n_id = json.load(i18n_file)
    return i18n_id


# after adding xlf json terms in, if there's some random uuid as id, need to remap to same id in html dynamic terms
def replace_i18n_id(i18n_id, terms, lang):
    for key, _ in terms.items():
        for id, new_id in i18n_id.items():
            if id in terms[key].keys():
                terms[key][new_id] = terms[key].pop(id)
    with open(f'./converted/{lang}.json', 'w') as output:
        json.dump(terms, output, ensure_ascii=False, indent=4, sort_keys=True)


# reformat json into suitable format for csv
def json_reformat(data):
    ct = datetime.datetime.now()
    result = []
    for loc in data.keys():
        for id in data[loc].keys():
            result.append({'Location': loc, 'Name': id, 'Value': data[loc][id], 'Timestamp': ct})
    return result


#  convert json into csv
def json_to_csv(lang_input):
    for lang in lang_input:
        with open(f'./converted/{lang}.json') as lang_file:
            data = json.load(lang_file)

        data = json_reformat(data)
        data_file = open(f'./csv/{lang}.csv', 'w', newline='')
        csv_writer = csv.writer(data_file)

        count = 0
        for data in data:
            if count == 0:
                header = data.keys()
                csv_writer.writerow(header)
                count += 1
            csv_writer.writerow(data.values())
        data_file.close()


# setup credential for google drive access, requires token.json
def setup():
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return creds


#  get all file id that needs to be updated in translation
def query(creds, folder_id):
    try:
        service = build('drive', 'v3', credentials=creds)

        # Call the Drive v3 API
        results = service.files().list(
            q=f"mimeType='application/vnd.google-apps.spreadsheet' and '{folder_id}' in parents and trashed = false",
            fields="nextPageToken, files(id, name)").execute()
        items = results.get('files', [])

        if not items:
            print('No files found.')
            return {}
        return items
    except HttpError as error:
        print(f'An error occurred: {error}')


# first time upload language file - do it once only when new language added
# lang_input: list of lang to upload
def upload(folder_id, lang_input):
    creds = setup()
    try:
        service = build('drive', 'v3', credentials=creds)
        for lang in lang_input:
            file_metadata = {
                'title': lang,
                'mimeType': 'application/vnd.google-apps.spreadsheet',
                'name': lang,
                'parents': [folder_id]
            }
            media = MediaFileUpload(f'./csv/{lang}.csv', mimetype='text/csv',
                                    resumable=True)
            file = service.files().create(body=file_metadata, media_body=media,
                                        fields='id').execute()
            print(F'File with ID: "{file.get("id")}" has been uploaded.')
    except HttpError as error:
        print(f'An error occurred: {error}')


# update all google sheets in translation google drive
def update(folder_id):
    creds = setup()
    files = query(creds, folder_id)
    try:
        service = build('drive', 'v3', credentials=creds)
        for file in files:
            media = MediaFileUpload('./csv/' + file['name'] + '.csv', mimetype='text/csv', resumable=True)
            file = service.files().update(fileId=file['id'], media_body=media).execute()
            print(F'File: "{file.get("id")}" has been updated.')
    except HttpError as error:
        print(f'An error occurred: {error}')


# download from google drive and convert back into json
def download(folder_id):
    creds = setup()
    files = query(creds, folder_id)
    try:
        # create drive api client
        service = build('drive', 'v3', credentials=creds)    
        for file_id in files:
            request = service.files().export_media(fileId=file_id['id'], mimeType='text/csv')
            file = io.BytesIO()
            downloader = MediaIoBaseDownload(file, request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()
                print(f'Download {int(status.progress() * 100)}.')
            # save csv for update
            file.seek(0)
            df = pd.read_csv(file)
            df.to_csv('./csv/' + file_id['name'] + '.csv', index=False)
            # convert back into json
            updated = {}
            with open('./converted/' + file_id['name'] + '.json') as lang_file:
                current = json.load(lang_file)
            for _, row in df.iterrows():
                if row['Location'] not in updated.keys():
                    updated[row['Location']] = {}
                if row['Name'] not in updated[row['Location']].keys():
                    updated[row['Location']][row['Name']] = format_spacing(current[row['Location']][row['Name']], row['Value'])
            with open('./converted/' + file_id['name'] + '.json', 'w') as output:
                json.dump(updated, output, ensure_ascii=False, indent=4, sort_keys=True)
    except HttpError as error:
        print(F'An error occurred: {error}')
        file = None


def main():
    parser = argparse.ArgumentParser('i18n-to-ngx')
    parser.add_argument('src', type=Path)
    args = parser.parse_args(sys.argv[1:])
    
    # path to xlf files as args
    # convert_file(args.src)
    # convert_xlf_to_json(args.src)
    # translate_files()
    
    # folder_id as args 
    # json_to_csv([])
    # update(args.src.name)
    # download(args.src.name)
