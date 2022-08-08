# i18n-to-ngx

Scripts for translation [here](https://github.com/morbitech1/i18n-to-ngx).

### Steps to adding a new language
- Generate majority of the old terms from po editor in that language
- Export as xlf and rename according to google translate ISO-639-1 Code (eg. english is en.xlf)
- Use script to convert into json (get i18n_id.json, and then convert_xlf_to_json)
- Once converted, add new terms through translate_file in script and the json will be complete
- Lastly, add language to webpack comment in language service on our app, ensure the locale for number and dates works on the application
- Setup your own authentication key to use google drive api [here](https://www.youtube.com/watch?v=1y0-IfRW114)
- Convert into csv and upload new language to google drive, ensure permission set to link shareable and editable for outsourcing review

### Update translations for current languages
- Ensure all the jsons are into converted folder (if not create a converted folder)
- Add new term in en.json
- Use translate_file function in script to update other language json

### Removing translation terms
- Ensure all the jsons are into converted folder (if not create a converted folder)
- Create a list of translation terms to remove: [[location, id]] format
- Use the remove_translation(terms) function
