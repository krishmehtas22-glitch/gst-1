"""One registry for batch fallback and verified provider-cache selection."""
PROVIDERS=('Cerebras','Groq','Gemini')
INTERVALS={'Cerebras':2.1,'Groq':13,'Gemini':13}


def reader(provider):
    if provider=='Cerebras':from . import cerebras_reader as module
    elif provider=='Groq':from . import groq_reader as module
    elif provider=='Gemini':from . import gemini_reader as module
    else:raise ValueError('Unknown invoice API provider')
    return module
