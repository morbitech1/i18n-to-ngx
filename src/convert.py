import argparse
import sys
from pathlib import Path
from bs4 import BeautifulSoup
from functools import reduce
from bs4.formatter import HTMLFormatter
import re
from googletrans import Translator
import json

replacements = ['Us2Button', 'cdkDropListGroup', '[matTooltipClass]', '#relatedFindingRow', '[matTooltipPosition]']
#  these can only replace after the first round else it causes half lowercase statement like cdkDropListdropped
secondary_replacements = ['cdkDrag', 'cdkDropList', 'ngModel', 'matInput', 'matSort', 'matRipple', 'matTableExporter']
remove_tags = [r'</img>', r'=""']
#  'es', 'pt', 'ja', 'de', 'ms', 'ko', 'it', 'sv', 'da', 'no', 'th', 'vi', 'ar'
langs = ['fr', 'zh-CN', 'zh-TW', 'nl']
    

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
                mods[attr] = {'type': "[%s]" % (type_token), 'val': "'%s.%s' | translate : {default: '%s'}" % (loc.upper(), id, val)}
            else:
                val = reduce(lambda x, y: x + str(y), tag.contents)
                val = str(val).strip()
                if id == "":
                    val_list = val.split(' ')
                    if len(val_list) > 5:
                        id = ' '.join(val_list[:5])
                    else:
                        id = val
                tag.string = "{{ '%s.%s' | translate : {default: '%s'} }}" % (loc.upper(), id, val)
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
        tags = soup.findAll(lambda tag: any(e.find('i18n') != -1 for e in tag.attrs.keys()))
        mods = {}
        for tag in tags:
            mods = convert_tag(html_path, tag)
        # if there's no change, don't write anything
        if len(mods):
            write_html(html_path, soup)

# add back spacking base on original terms
def format_spacing(term, trans):
    if term[0] == ' ':
        trans = ' ' + trans
    if term[-1] == ' ':
        trans += ' '
    return trans


# compared json to en.json to find terms to translate and add
def translate_files():
    translator = Translator()
    result = {}
    untranslated = {}
    for lang in langs:
        lang_tag = lang.replace('-', '_')
        try:
            with open(f'./converted/{lang_tag}.json') as lang_file:
                result[lang] = json.load(lang_file)
        except Exception as e:
            result[lang] = {}
    with open(f'./converted/en.json') as lang_file:
        original = json.load(lang_file)
    for lang in langs:
        lang_tag = lang.replace('-', '_')
        for key, terms in original.items():
            for id, val in terms.items():
                if key not in result[lang].keys():
                    result[lang][key] = {}
                if id not in result[lang][key].keys():
                    try:
                        trans_term = translator.translate(val, dest=str(lang))
                        result[lang][key][id] = format_spacing(val, trans_term.text)
                    except Exception as e:
                        print(e)
                        if val in untranslated.keys():
                            untranslated[val].append(lang)
                        else:
                            untranslated[val] = [lang]
        # save all translated
        with open(f'./converted/{lang_tag}.json', 'w') as output:
            json.dump(result[lang], output, ensure_ascii=False)
    with open('./converted/untranslated.json', 'w') as output:
            json.dump(untranslated, output, ensure_ascii=False)


def convert_xlf_to_json(path: Path):
    paths = [path] if path.is_file() else list(path.glob('*.xlf'))
    for html_path in paths:
        lang = html_path.stem.split('.')[-1]
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
                            locs = filter(lambda x: x != 'component', reduce(lambda x, y: x + str(y), inner_c.contents).split('/')[-1].split('.')[:-1])
                            loc = '.'.join(locs).upper()
                            loc = loc.replace('-', '_')
                            if loc not in result.keys():
                                result[loc] = {}
                            if val not in result[loc].values():
                                result[loc][id] = val
        with open(f'./converted/{lang}.json', 'w') as outfile:
            json.dump(result, outfile, ensure_ascii=False)


# after adding xlf json terms in, if there's some random uuid as id, need to remap to same id in html dynamic terms
def convert_i18n_id():
    i18n_id = {}
    result = {}
    with open(f'./converted/en.json') as lang_file:
        original = json.load(lang_file)
    for _, terms in original.items():
        for id, val in terms.items():
            # identify i18n uuid
            if len(id) == 40:
                if len(id.split(' ')) == 1 and len(id.split('_')) == 1 and len(id.split('-')) == 1:
                    print(val)
                    print('')
                    new_id = ''
                    val_list = val.split(' ')
                    if len(val_list) > 5:
                        new_id = ' '.join(val_list[:5])
                    else:
                        new_id = val
                    i18n_id[id] = new_id
    langs.append('en')
    for lang in langs:
        lang_tag = lang.replace('-', '_')
        try:
            with open(f'./converted/{lang_tag}.json') as lang_file:
                result[lang] = json.load(lang_file)
        except Exception as e:
            result[lang] = {}
        for key, terms in result[lang].items():
            for id, new_id in i18n_id.items():
                if id in result[lang][key].keys():
                    result[lang][key][new_id] = result[lang][key].pop(id)
        with open(f'./converted/{lang_tag}.json', 'w') as output:
            json.dump(result[lang], output, ensure_ascii=False)

def main():
    parser = argparse.ArgumentParser('i18n-to-ngx')
    parser.add_argument('src', type=Path)
    args = parser.parse_args(sys.argv[1:])
    # convert_file(args.src)
    # translate_files()
    # convert_xlf_to_json(args.src)
    # convert_i18n_id()
