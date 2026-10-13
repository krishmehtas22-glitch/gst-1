"""One registry for batch fallback and verified provider-cache selection."""
ACTIVE_PROVIDERS=('GitHub Models','Groq','Gemini')
PROVIDERS=ACTIVE_PROVIDERS+('Cerebras',)  # Retain access to old source caches.
INTERVALS={'GitHub Models':4.1,'Cerebras':2.1,'Groq':13,'Gemini':13}
KEY_VARIABLES={'GitHub Models':'GITHUB_MODELS_TOKEN','Cerebras':'CEREBRAS_API_KEY',
               'Groq':'GROQ_API_KEY','Gemini':'GEMINI_API_KEY'}


def reader(provider):
    if provider=='GitHub Models':from . import github_models_reader as module
    elif provider=='Cerebras':from . import cerebras_reader as module
    elif provider=='Groq':from . import groq_reader as module
    elif provider=='Gemini':from . import gemini_reader as module
    else:raise ValueError('Unknown invoice API provider')
    return module
