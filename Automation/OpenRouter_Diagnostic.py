"""Check free-only OpenRouter access without uploading invoice data."""
import os
from Common_Rules.openrouter_reader import api_json,configured_model


def diagnose(transport=api_json):
    key=os.environ.get('OPENROUTER_API_KEY','').strip()
    lines=['OpenRouter diagnostic — no invoice uploaded','OPENROUTER_API_KEY present: '+('yes (hidden)' if key else 'no')]
    if not key:return lines+['Set OPENROUTER_API_KEY privately in Windows user environment variables and reopen the app.']
    stage='free-only configuration'
    try:
        model=configured_model();lines.append('Model: '+model)
        stage='model-list request'
        data=transport('models',key,timeout=20)
        models=data.get('data',[])
        if not isinstance(models,list):raise ValueError('Unexpected model catalog')
        free=[]
        for item in models:
            if not isinstance(item,dict):continue
            name=item.get('id','');pricing=item.get('pricing',{})
            if isinstance(name,str) and (name=='openrouter/free' or name.endswith(':free')) and isinstance(pricing,dict):
                try:
                    if all(float(pricing.get(field,'1'))==0 for field in ('prompt','completion')):free.append(name)
                except (TypeError,ValueError):pass
        lines.append('Free catalog models: '+str(len(free)))
        if model!='openrouter/free' and model not in free:
            return lines+['Configured free model not listed with zero prompt/completion prices. No generation requested.']+free[:30]
        stage='one small free JSON request'
        payload={'model':model,'messages':[{'role':'user','content':'Return JSON only: {"ok":true}'}],
                 'temperature':0,'max_tokens':256,'response_format':{'type':'json_object'},
                 'provider':{'max_price':{'prompt':0,'completion':0}}}
        response=transport('chat/completions',key,payload,timeout=40)
        choices=response.get('choices',[])
        lines.append('Small JSON request: '+('succeeded' if choices and choices[0].get('finish_reason')=='stop' else 'no complete response'))
        lines.append('Only free routing was requested. Account/provider limits still apply; no paid fallback is enabled.')
        lines.append('This checks access, not invoice accuracy.')
    except (ValueError,KeyError,TypeError) as exc:lines.append('Failed at '+stage+': '+str(exc))
    return lines


if __name__=='__main__':
    print('\n'.join(diagnose()))
    print('Share these result lines only; never share API keys.')
