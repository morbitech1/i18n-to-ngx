# i18n-to-ngx

### Steps to adding a new language
- Generate majority of the old terms from po editor in that language
- Export as xlf and use script to convert from xlf to json
- Once converted, add new terms through translate_file in script and the json will be complete
- Lastly, add language to webpack comment in language service on our app, ensure the locale for number and dates works on the application

### Update translations for current languages
- Ensure all the jsons are in converted folder
- Add new term in en.json
- Use translate_file function in script to update other language json

### Removing translation terms
- Ensure all the jsons are in converted folder
- Create a list of translation terms to remove: [[location, id]] format
- Use the remove_translation(terms) function
