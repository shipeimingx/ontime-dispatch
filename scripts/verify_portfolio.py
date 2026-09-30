"""Verify saved artifact provenance and independent history/future gates (no new search)."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from ontime.evaluate import check_plan, parse_plan
from ontime.input import as_problem
from ontime.replan import validate_replanning


def verify(directory, output_file=None):
    from PIL import Image
    directory=Path(directory)
    run=json.loads((directory/'run.json').read_text(encoding='utf-8'))
    manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    raw=json.dumps(run['input_snapshot'],sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')
    assert hashlib.sha256(raw).hexdigest()==run['input_snapshot_sha256']==manifest['input_sha256']
    problem=as_problem(run['input_snapshot'])
    for phase in ('initial','ga'):
        plan=parse_plan(problem,run[phase]['plan_input'],run['mode'],run['parameters']['seed'])
        assert check_plan(problem,plan).valid
    baseline=parse_plan(problem,run['ga']['plan_input'],run['mode'],run['parameters']['seed'])
    replan=json.loads((directory/'replan/replan.json').read_text(encoding='utf-8'))
    candidate=parse_plan(problem,replan['combined']['plan_input'],run['mode'],run['parameters']['seed'])
    assert validate_replanning(problem,baseline,candidate,replan['checkpoint_s'],replan['unavailable_vehicle_id'])['valid']
    assert replan['approval_status']=='not_approved' and not replan['execution_started']
    ns={'s':'http://www.w3.org/2000/svg'}
    for figure in manifest['figures']:
        file=directory/'figures'/figure['svg']
        tree=ET.parse(file)
        metadata=json.loads(tree.find('s:metadata',ns).text)
        assert metadata['input_sha256']==run['input_snapshot_sha256']
        assert tree.findall('s:text',ns)  # SVG has editable text, not a raster disguised as SVG.
        assert {n.attrib['font-family'] for n in tree.findall('s:text',ns)} <= {'Source Han Sans CN','Sarasa Mono SC'}
        assert not tree.findall('s:image',ns)
        with Image.open(directory/'figures'/figure['png']) as img:
            assert list(img.size)==figure['png_dimensions']
            img.verify()
    for path,digest in manifest['files_sha256'].items():
        assert hashlib.sha256((directory/path).read_bytes()).hexdigest()==digest,path
    for path,digest in manifest['source_sha256'].items():
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest,path
    summary={'artifact_checks_passed':True,'figures_verified':len(manifest['figures']),
             'input_sha256':manifest['input_sha256'],'replan_temporal_gate_valid':True,
             'manifest_sha256':hashlib.sha256((directory/'manifest.json').read_bytes()).hexdigest(),
             'checks':['SVG XML and editable text','requested font family declarations',
                       'PNG readability and dimensions','normalized input SHA256',
                       'all recorded output and source SHA256','initial/GA independent physical validation',
                       'replanning independent historical/residual/temporal validation',
                       'replanning remains unapproved']}
    if output_file:
        output_file=Path(output_file)
        output_file.parent.mkdir(parents=True,exist_ok=True)
        output_file.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory',type=Path,nargs='?',default=ROOT/'outputs/portfolio')
    p.add_argument('--output-file',type=Path)
    args=p.parse_args()
    verify(args.directory,args.output_file)
