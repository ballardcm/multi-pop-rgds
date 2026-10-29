#!/usr/bin/env python3
"""Relay the monorepo's RG DS releases over a localhost-only SSH tunnel.

Used for private testing and handhelds without Internet access. Authenticate gh on
this computer; no GitHub credential is returned to the handheld. `/releases` serves
the filtered list the updater reads and `/release` the newest entry alone. With
--prerelease or --tag the relay also serves a release the public API hides, and
clears its prerelease and draft flags so a test device will install it.
"""
import argparse, http.server, json, pathlib, re, shutil, subprocess, tempfile, threading
REPO='ballardcm/multi-pop'
TAG=re.compile(r'rgds-(\d{2})\.(\d{2})\.(\d{2})\.(\d{1,3})')
ASSET=re.compile(r'SHA256SUMS|multi-pop-rgds-rocknix-[0-9]+\.zip')
def newest_first(release):
    mm,dd,yy,rev=(int(x) for x in TAG.fullmatch(release['tag_name']).groups());return (yy,mm,dd,rev)
class Handler(http.server.BaseHTTPRequestHandler):
    def releases(self):
        server=self.server
        found=json.loads(subprocess.check_output(['gh','api',f'repos/{server.repo}/releases?per_page=100'],stderr=subprocess.PIPE))
        if server.tag:
            # A named tag is served whatever its state, so an unpublished build can be tried on one device first.
            chosen=[r for r in found if r['tag_name']==server.tag]
        else:
            chosen=[r for r in found if TAG.fullmatch(r['tag_name']) and not r.get('draft') and (server.prerelease or not r.get('prerelease'))]
            chosen.sort(key=newest_first,reverse=True)
        served=[]
        with server.guard:
            for release in chosen:
                assets=[]
                for a in release.get('assets',[]):
                    if ASSET.fullmatch(a['name']):
                        server.allowed.add(a['id'])
                        assets.append({'name':a['name'],'browser_download_url':f'http://127.0.0.1:{server.server_port}/asset/{a["id"]}'})
                served.append({'tag_name':release['tag_name'],'draft':False,'prerelease':False,'assets':assets})
        return served
    def send_json(self,value):
        data=json.dumps(value).encode()
        self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def do_GET(self):
        try:
            if self.path.split('?')[0]=='/releases':self.send_json(self.releases())
            elif self.path=='/release':
                # A single object keeps older updaters, which read releases/latest, working against the relay.
                served=self.releases()
                if not served:self.send_error(404,'No matching release');return
                self.send_json(served[0])
            elif re.fullmatch(r'/asset/[0-9]+',self.path):
                asset_id=int(self.path.rsplit('/',1)[1])
                with self.server.guard:
                    if asset_id not in self.server.allowed:self.send_error(404);return
                    path=self.server.cache/str(asset_id)
                    if not path.exists():
                        tmp=path.with_suffix('.tmp')
                        with tmp.open('wb') as out:
                            subprocess.run(['gh','api',f'repos/{self.server.repo}/releases/assets/{asset_id}','-H','Accept: application/octet-stream'],stdout=out,stderr=subprocess.PIPE,check=True)
                        tmp.replace(path)
                self.send_response(200);self.send_header('Content-Length',str(path.stat().st_size));self.end_headers()
                with path.open('rb') as source:shutil.copyfileobj(source,self.wfile)
            else:self.send_error(404)
        except (subprocess.CalledProcessError,ValueError,OSError):
            self.send_error(502,'GitHub release unavailable; check gh authentication and connectivity on the host.')
    def log_message(self,fmt,*args):print(fmt%args,flush=True)
def main():
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--port',type=int,default=18765)
    parser.add_argument('--repo',default=REPO,help='repository to relay (default %(default)s)')
    parser.add_argument('--prerelease',action='store_true',help='include RG DS prereleases in the list')
    parser.add_argument('--tag',help='serve only this release, even a draft, prerelease or non-RG DS tag')
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='multi-pop-relay-') as tmp:
        server=http.server.ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
        server.cache=pathlib.Path(tmp);server.allowed=set();server.guard=threading.Lock()
        server.repo=args.repo;server.prerelease=args.prerelease;server.tag=args.tag
        print(f'Relay for {args.repo}'+(f' tag {args.tag}' if args.tag else ' RG DS releases'+(' with prereleases' if args.prerelease else ''))+f' listening only on 127.0.0.1:{args.port}',flush=True)
        server.serve_forever()
if __name__=='__main__':main()
