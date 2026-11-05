"""Download the official pinned portable CAD runtime into this project only."""
import hashlib,json,subprocess,time
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1];DIRECTORY=ROOT/'tools/freecad'
NAME='FreeCAD_1.1.4-Windows-x86_64-py311.7z'
URL='https://github.com/FreeCAD/FreeCAD/releases/download/1.1.4/'+NAME
SHA256='4828741fc91ee37fafcdb97a1abacb18b04ba451ac4372d9ff7a7349b36f4d6d'


def main():
    DIRECTORY.mkdir(parents=True,exist_ok=True);archive=DIRECTORY/NAME
    if not archive.exists():
        temporary=archive.with_suffix('.7z.part');downloaded=0;last=time.monotonic()
        with requests.get(URL,stream=True,timeout=(30,180)) as response:
            response.raise_for_status();total=int(response.headers.get('Content-Length',0))
            with temporary.open('wb') as stream:
                for chunk in response.iter_content(1024*1024):
                    stream.write(chunk);downloaded+=len(chunk)
                    if time.monotonic()-last>10:
                        print(f'Downloaded {downloaded/1024**2:.1f} / {total/1024**2:.1f} MiB',flush=True);last=time.monotonic()
        temporary.replace(archive)
    digest=hashlib.file_digest(archive.open('rb'),'sha256').hexdigest()
    if digest!=SHA256:raise RuntimeError('Official archive SHA-256 mismatch; archive was not executed')
    record=dict(release='1.1.4',url=URL,official_release='https://github.com/FreeCAD/FreeCAD/releases/tag/1.1.4',
        official_asset_listing='https://github.com/FreeCAD/FreeCAD/releases/expanded_assets/1.1.4',
        sha256=digest,expected_sha256=SHA256,verified=True)
    (DIRECTORY/'download_manifest.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    print('Official SHA-256 verified',digest,flush=True)
    listing=subprocess.run(['tar','-tf',str(archive)],capture_output=True,text=True,encoding='utf-8')
    if listing.returncode:raise RuntimeError('System tar cannot read the portable archive: '+listing.stderr)
    destination=DIRECTORY/'runtime';destination.mkdir(exist_ok=True)
    for name in listing.stdout.splitlines():
        target=(destination/name).resolve()
        if not target.is_relative_to(destination.resolve()):raise RuntimeError('Archive member outside portable runtime')
    executables=[p for p in destination.rglob('FreeCADCmd.exe') if p.parent.name=='bin']
    if not executables:
        print('Extracting portable runtime',flush=True)
        subprocess.run(['tar','-xf',str(archive),'-C',str(destination)],check=True)
        executables=[p for p in destination.rglob('FreeCADCmd.exe') if p.parent.name=='bin']
    if len(executables)!=1:raise RuntimeError('Expected exactly one portable FreeCADCmd.exe')
    config=dict(executable=str(executables[0].resolve()),arguments=['{script}'],samples=50000,timeout_seconds=180,
        max_stl_faces=3000,representation='surface')
    (ROOT/'configs/freecad.local.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
    print('Configured',config['executable'],flush=True)


if __name__=='__main__':main()
