# AI Council

> For setup problems, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

A multi-agent decision framework that uses a council of AI experts to analyze decisions and produce structured directives with guardrails, with automatic Groq model fallback.

## ⚡ Key Features

### Intelligent Auto-Switching
- **Zero Configuration Required**: Models automatically switch when rate limits or errors occur
- **All Free Models**: Uses only free Groq models (no API costs)
- **Seamless Fallbacks**: Automatic retry with next available model in the chain
- **Full Transparency**: UI shows when models were auto-switched

### Current Fallback Chain
1. `openai/gpt-oss-20b` - fast default model
2. `openai/gpt-oss-120b` - higher-capability fallback

When a model fails (rate limit, timeout, or availability error), the system automatically switches to the next supported model in the chain.

## Architecture

- **Backend**: FastAPI service with async LLM orchestration and intelligent retry logic
- **Frontend**: Streamlit web interface with no manual model selection
- **Primary Provider**: Groq with automatic fallback
- **Fallback Strategy**: Automatic switching between current production models

## Quick Start

> This README is the complete setup and product guide.

### Easy Start (Recommended)

**Windows:**
```powershell
# 1. Add your Groq API key to .env
Copy-Item .env.example .env
# Edit .env and add: GROQ_API_KEY=your_key_here

# 2. Start everything
.\start_all.ps1
```

**Linux/Mac:**
```bash
# 1. Add your Groq API key to .env
cp .env.example .env
# Edit .env and add: GROQ_API_KEY=your_key_here

# 2. Start backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload &

# 3. Start frontend (new terminal)
cd frontend
pip install -r requirements.txt
streamlit run app.py
```

### Docker

```bash
docker-compose up --build
```

### What You Need

- **Python 3.11+** - [Download here](https://www.python.org/downloads/)
- **Groq API Key** - Free at [console.groq.com](https://console.groq.com/keys)
- **2 minutes** - That's it!

## How Auto-Switching Works

### Automatic Failover Process
1. A council member starts with the configured model (e.g., `openai/gpt-oss-20b`)
2. If the model encounters an error (429 rate limit, 503 service error, timeout):
   - System **automatically** switches to the next free model in the chain
   - Retry happens **immediately** with no delay
   - User sees **zero errors** - just a seamless response
3. UI displays which model was used and if it was auto-switched

### Error Types That Trigger Auto-Switch
- **429 Rate Limit Exceeded**: Immediate switch to next model
- **503 Service Unavailable**: Auto-retry with fallback
- **502 Bad Gateway**: Switch to alternative model
- **Timeout**: Retry with different model
- **Connection Errors**: Automatic fallback
- **Empty Response**: Switch to next available model

### Example Flow
```
User asks question
  → Operator tries openai/gpt-oss-20b
  → Rate limited (429)
  → Auto-switches to openai/gpt-oss-120b ⚡
  → Success!
  → UI shows: "groq / openai/gpt-oss-120b ⚡ auto-switched from openai/gpt-oss-20b"
```

## Configuration

All configuration is via environment variables. See `.env.example` for all options.

### Essential Settings (Minimal Setup)
```bash
# Only this is required for basic operation:
GROQ_API_KEY=your_groq_api_key_here
```

### Optional Settings
- `API_KEY` - Backend authentication key (required in production)
- `ALLOWED_ORIGINS` - CORS origins (default: `http://localhost:8501`)
- `RATE_LIMIT_REQUESTS` and `RATE_LIMIT_WINDOW` - Rate limiting (default: 10 requests per 60 seconds)
- `ENVIRONMENT` - `development` or `production`

### Model Configuration (Advanced)
You can customize which free Groq model each council member starts with:
```bash
EXPERT_OPERATOR_MODEL=openai/gpt-oss-20b
EXPERT_ANALYST_MODEL=openai/gpt-oss-120b
EXPERT_RISK_MODEL=openai/gpt-oss-20b
EXPERT_RESEARCHER_MODEL=openai/gpt-oss-120b
```

**Note**: Automatic fallback tries the other supported model if the configured model is unavailable.

## API Endpoints

- `GET /v1/health` - Health check (shows provider status)
- `POST /v1/ask` - Submit a decision for council deliberation
  - Form data: `prompt`, `debate` (optional), `sources` (optional newline-separated HTTP(S) links)
  - No `model_overrides` needed - automatic switching handles everything

## Security Features

- API key authentication
- Rate limiting (10 req/min default)
- CORS restriction
- Prompt injection detection
- SSRF protection on frontend
- Input sanitization
- Production error sanitization

## Testing

```bash
# Backend tests
cd backend
pip install -r requirements-dev.txt
pytest tests/ -v

# Frontend tests
cd frontend
pip install -r requirements-dev.txt
pytest tests/ -v
```

## Council Members

### Phase I: Independent Analysis
1. **The Operator** - Practical execution and feasibility
2. **The Decision Analyst** - Trade-off evaluation and criteria analysis
3. **The Risk Officer** - Safety guardrails and downside protection
4. **The Evidence Reviewer** - Fact checking and knowledge gaps

### Phase II: Challenge Round
Council members review peer positions, challenge assumptions, and issue final positions.

### Final Synthesis
**The Chairman** produces one decisive directive with:
- Single clear recommendation
- Why it wins against decision criteria
- 3-step execution plan
- Guardrails and reversal triggers
- Confidence level and key uncertainty

## Project Structure

```
AI-Council/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app (no model_overrides)
│   │   ├── council.py       # Auto-switching logic in _call_text()
│   │   ├── config.py        # GROQ_FALLBACK_CHAIN defined here
│   │   ├── schemas.py       # MemberResponse includes switched_from_model
│   │   ├── clients.py       # LLM provider clients
│   │   ├── cache.py         # Thread-safe TTL cache
│   │   └── observability.py # Structured logging + metrics
│   ├── tests/
│   ├── Dockerfile
│   └── requirements*.txt
├── frontend/
│   ├── app.py               # Streamlit app (no model selection sidebar)
│   │                        # Shows auto-switch indicator: ⚡
│   ├── api/                 # Typed API client (no model_overrides param)
│   ├── utils/               # Sanitization utilities
│   ├── constants.py         # No GROQ_MODELS or COUNCIL_MEMBER_KEYS
│   ├── tests/
│   ├── Dockerfile
│   └── requirements*.txt
├── docker-compose.yml
├── .github/workflows/
└── .env.example
```

## Why This Approach?

### Benefits of Automatic Switching
✅ **Zero User Configuration**: No dropdowns, no model selection complexity  
✅ **Maximum Reliability**: Multiple fallback models ensure high availability  
✅ **Cost Efficient**: All models in the chain are 100% free  
✅ **Transparent**: UI clearly shows when auto-switching occurred  
✅ **Resilient**: Handles rate limits, timeouts, and service errors gracefully  
✅ **Production Ready**: No manual intervention needed when models fail  

### Previous Approach (Removed)
❌ Manual model selection sidebar  
❌ User responsible for choosing models  
❌ Errors shown when models fail  
❌ Complex UI with 6+ model dropdowns  

## Troubleshooting

### "Rate limit exceeded" still showing?
This shouldn't happen with auto-switching enabled. If you see this:
1. Check that `GROQ_FALLBACK_CHAIN` in `backend/app/config.py` contains the two current model IDs
2. Verify your Groq API key is valid
3. Check backend logs to see the fallback chain execution

### All models failing?
If both configured Groq models fail, check:
1. Groq API status: https://status.groq.com
2. Your API key is correctly set in `.env`
3. No network/firewall issues blocking api.groq.com

### Want to see which model was used?
Check the council member cards - they display the final model used and show "⚡ auto-switched from X" if fallback occurred.

## License

MIT
