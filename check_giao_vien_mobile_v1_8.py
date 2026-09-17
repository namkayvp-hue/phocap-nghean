from pathlib import Path
from jinja2 import Environment, FileSystemLoader
root=Path(r'C:\\PhoCap\\app\\templates')
env=Environment(loader=FileSystemLoader(str(root)))
for name in ['surveys/index.html','surveys/households.html','surveys/quick_entry.html']:
    env.get_template(name)
print('Jinja templates: DAT')
