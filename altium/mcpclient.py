import json,os,subprocess,sys
# Path to the altium-designer-mcp binary (build: cargo build --release in embedded-society/altium-designer-mcp)
BIN=os.environ.get('ALTIUM_MCP_BIN','altium-designer-mcp')
class MCP:
    def __init__(s,allow):
        s.p=subprocess.Popen([BIN,'--allow',allow,'-q'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
        s.i=0
        s.req('initialize',{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'client','version':'1'}})
        s.p.stdin.write(json.dumps({'jsonrpc':'2.0','method':'notifications/initialized'})+'\n');s.p.stdin.flush()
    def req(s,m,params):
        s.i+=1
        s.p.stdin.write(json.dumps({'jsonrpc':'2.0','id':s.i,'method':m,'params':params})+'\n');s.p.stdin.flush()
        while True:
            r=json.loads(s.p.stdout.readline())
            if r.get('id')==s.i: return r
    def call(s,name,args):
        r=s.req('tools/call',{'name':name,'arguments':args})
        if 'error' in r: return {'ERROR':r['error']}
        c=r['result']; txt=''.join(x.get('text','') for x in c.get('content',[]))
        try: out=json.loads(txt)
        except Exception: out=txt
        if c.get('isError'): return {'ERROR':out}
        return out
