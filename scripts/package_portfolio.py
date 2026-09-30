"""Package Python source, illustrative inputs, actual outputs, figures and fonts."""
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'outputs/delivery/ontime-dispatch-2026-portfolio.zip'
DEST.parent.mkdir(parents=True,exist_ok=True)
files=set()
for folder in ('src/ontime','tests','docs','scripts','assets/fonts','outputs/portfolio','outputs/validation',
               'outputs/cases','outputs/ga'):
    for file in (ROOT/folder).rglob('*'):
        if file.is_file() and '__pycache__' not in file.parts and file.suffix not in ('.7z','.pyc','.mjs'):
            files.add(file)
for name in ('README.md','run_ontime.py','Run-OnTime-Python.cmd','Run-Validation.cmd','Build-Portfolio.cmd',
             'requirements-presentation.txt','data/portfolio.json','data/demo_2026.json'):
    files.add(ROOT/name)
files.update((ROOT/'data/cases').glob('*.json'))
with zipfile.ZipFile(DEST,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
    for file in sorted(files):
        archive.write(file,str(file.relative_to(ROOT)))
with zipfile.ZipFile(DEST) as archive:
    damaged=archive.testzip()
    if damaged:
        raise RuntimeError('Damaged archive member: '+damaged)
print(f'Packaged {len(files)} files: {DEST} ({DEST.stat().st_size} bytes). Archive CRC verified.')
