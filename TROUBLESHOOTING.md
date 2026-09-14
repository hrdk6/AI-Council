# 🔧 Troubleshooting Guide - AI Council

Common issues and solutions for AI Council.

## Table of Contents
- [Installation Issues](#installation-issues)
- [Startup Problems](#startup-problems)
- [Runtime Errors](#runtime-errors)
- [Performance Issues](#performance-issues)
- [Auto-Switching Issues](#auto-switching-issues)
- [Development Issues](#development-issues)

---

## Installation Issues

### Python Version Error

**Symptom:**
```
ERROR: Python 3.11 or higher is required
```

**Solution:**
1. Check your Python version: `python --version`
2. Install Python 3.11+ from [python.org](https://www.python.org/downloads/)
3. Make sure to add Python to PATH during installation

### Dependency Installation Fails

**Symptom:**
```
ERROR: Could not find a version that satisfies the requirement...
```

**Solutions:**

**Option 1: Upgrade pip**
```powershell
python -m pip install --upgrade pip
cd backend
pip install -r requirements.txt
```

**Option 2: Use virtual environment**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

**Option 3: Install problematic package separately**
```powershell
# Common culprits
pip install --upgrade setuptools wheel
pip install fastapi uvicorn
```

---

## Startup Problems

### Backend Won't Start

**Symptom:**
```
ModuleNotFoundError: No module named 'app'
```

**Solution:**
```powershell
# Make sure you're in the backend directory
cd backend
python -m uvicorn app.main:app --reload
```

### Port Already in Use

**Symptom:**
```
ERROR: [Errno 10048] Only one usage of each socket address
```

**Solutions:**

**Option 1: Kill existing process**
```powershell
# Find processes using port 8000
netstat -ano | findstr :8000
# Kill process (replace PID with actual number)
taskkill /F /PID <PID>
```

**Option 2: Use different port**
```powershell
# Backend on different port
uvicorn app.main:app --reload --port 8001

# Then open http://localhost:8001 (the web interface is served from the same port)
```

### Missing .env File

**Symptom:**
```
WARNING: Missing provider API keys: groq (GROQ_API_KEY)
```

**Solution:**
```powershell
# Create .env file from example
Copy-Item .env.example .env

# Edit .env and add your key
# GROQ_API_KEY=your_key_here
```

**Get a free Groq API key:** https://console.groq.com/keys

### "Can't reach the council server"

**Symptom:** The page loads but shows this message, or the page doesn't load at all.

**Solution:**
1. **Check the server is running**: visit http://localhost:8000/v1/health
2. **Start it**: `.\start_all.ps1`
3. **Check the firewall**: allow localhost connections
4. **Web interface missing?** If `/v1/health` works but `/` returns 404, the server log says
   "Web interface not found". Run from the repository so `frontend/public` exists, or set `FRONTEND_DIR`.

### Backend Refuses to Start in Production

**Symptom:**
```
pydantic_core._pydantic_core.ValidationError: ... API_KEY must be set when ENVIRONMENT=production.
```

**Solution:** Set `API_KEY` to a long random string, or use `ENVIRONMENT=development` locally.
```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```
Other settings are validated the same way. The error names the offending variable (for example
`rate_limit_requests` means `RATE_LIMIT_REQUESTS`).

---

## Runtime Errors

### "The access key wasn't accepted"

**Cause:** The server has `API_KEY` set, and the key entered in the browser doesn't match it.

**Solution:** Click **Access key** at the top of the page and enter the exact `API_KEY` value. If you ticked
"Remember on this device" with an old key, entering the new one replaces it.

### Uploaded evidence shows "couldn't be read"

The reason is shown under the file name:

| Message | What to do |
|---------|------------|
| Password-protected | Remove the password (for example, print to PDF) and upload again. |
| Damaged | Re-export the PDF or image; the file isn't valid. |
| No selectable text, and reading scanned pages is turned off | Set `MAX_OCR_PAGES` above 0. |
| The vision model couldn't read this file | Check that `VISION_MODELS` lists models your Groq key can use, then retry. |

To see which vision models your key can reach:
```powershell
cd backend
python -c "import asyncio,os;from dotenv import load_dotenv;load_dotenv('.env');from openai import AsyncOpenAI;c=AsyncOpenAI(base_url='https://api.groq.com/openai/v1',api_key=os.environ['GROQ_API_KEY']);print([m.id for m in asyncio.run(c.models.list()).data])"
```

### Statements look cut off, or members "couldn't take part" with empty responses

**Cause:** `gpt-oss` models reason before answering, and those reasoning tokens count against
`*_MAX_TOKENS`. At higher reasoning effort they can use the whole budget and return nothing.

**Solution:** Keep `REASONING_EFFORT=low` (the default), or raise `EXPERT_*_MAX_TOKENS` and `CHAIRMAN_MAX_TOKENS`.
Higher budgets use more of the free tier's tokens-per-minute allowance.

### "No council member could respond" (503)

**Symptom:**
```
No council member could respond. The model providers may be rate-limited or misconfigured; please retry shortly.
```

**Causes & Solutions:**

**1. Invalid API Key**
```powershell
# Check your .env file
cat .env
# Verify GROQ_API_KEY is correct
```

**2. Rate Limits Exceeded (All Fallback Models)**
- **Wait 1 minute** - Free tier limits reset quickly
- **Try again** - Limits are per-minute
- **Consider Groq Pro** - Higher limits for production

**3. Groq Service Down**
- Check status: https://status.groq.com
- Wait for service restoration
- Use alternative provider (if configured)

### "Rate limit reached" (429)

**Cause:** This is the backend's own per-IP limit (`RATE_LIMIT_REQUESTS` per `RATE_LIMIT_WINDOW`
seconds), not Groq's. Users behind the same proxy or office network share one IP address.

**Solution:** Wait for the window to reset, or raise `RATE_LIMIT_REQUESTS` for multi-user deployments.

Provider-side 429s are retried and walk the Groq fallback chain automatically. To check the chain:
```powershell
cd backend
python -c "from app.config import GROQ_FALLBACK_CHAIN; print(GROQ_FALLBACK_CHAIN)"
# ('openai/gpt-oss-20b', 'openai/gpt-oss-120b') unless GROQ_FALLBACK_CHAIN overrides it
```

### Prompt Injection Detected

**Symptom:**
```
Invalid prompt: potential injection attempt detected.
```

**Cause:** Your prompt contains patterns used to hijack model instructions (for example
"ignore previous instructions" or "reveal your system prompt"). Ordinary questions that mention
system prompts are allowed.

**Solution:**
- Remove phrases like "ignore previous instructions"
- Avoid system-like commands in your question
- Ask naturally: "Should I invest in X or Y?"

## Performance Issues

### Slow Response Times

**Symptom:** Council takes >30 seconds to respond

**Possible Causes:**

**1. First Request After Startup**
- ✅ **Normal** - First request is slower (cold start)
- Subsequent requests are faster

**2. Network Issues**
- Check internet connection
- Try different network
- Check Groq API status

**3. Model Switching**
- If switching multiple times, adds latency
- Normal: ~2-5 seconds
- With switches: ~5-10 seconds

### High Memory Usage

**Symptom:** Python process using excessive RAM

**Solutions:**

**1. Clear Cache**
```powershell
# Backend cache stored in memory
# Restart backend to clear
```

**2. Reduce Cache Size** (in .env)
```bash
COUNCIL_CACHE_MAXSIZE=50  # Default: 200
```

**3. Limit Concurrent Debate**
```bash
DEBATE_CONCURRENCY_LIMIT=1  # Default: 2
```

---

## Auto-Switching Issues

### See which models are paused

Open `/v1/providers` on your server (for example `https://your-app.onrender.com/v1/providers`). The `models`
list shows every model the council may use, with `"status": "paused"`, the reason, and `retry_in_s` for any model
being skipped. Pauses clear on their own; restarting the server clears them immediately.

### Old two-model chain in your environment

If your `.env` or Render environment still sets `GROQ_FALLBACK_CHAIN=openai/gpt-oss-20b,openai/gpt-oss-120b`,
it overrides the new four-model default. Remove the variable or add `qwen/qwen3.8-27b,qwen/qwen3.6-27b`.

### Adding backups from another provider

Set that provider's key (for example `GEMINI_API_KEY`) and `BACKUP_MODELS=gemini:gemini-2.5-flash`. Backups on a
provider without a key are skipped silently, so a typo in the key name means they're never used.

### Not Seeing ⚡ Indicator

**Symptom:** Models switch but no indicator shows

**Check:**
1. **Backend Response**: `switched_from_model` field should be present
2. **Browser cache**: hard refresh so the latest interface scripts load
3. **Browser Cache**: Hard refresh (Ctrl+Shift+R)

### Models Not Switching

**Symptom:** Get errors instead of automatic fallback

**Debug Steps:**

**1. Check fallback chain:**
```powershell
cd backend
python -c "from app.config import GROQ_FALLBACK_CHAIN; print('Models:', len(GROQ_FALLBACK_CHAIN))"
# Default: Models: 2
```

**2. Check error detection:**
```powershell
# Look at backend logs
# Transient errors log "auto-switching to ...".
# "non-retriable error" means an auth or request problem (e.g. 401/400) that switching cannot fix.
```

**3. Verify Groq provider:**
```powershell
python -c "from app.council import EXPERT_LIBRARY; print([x.provider for x in EXPERT_LIBRARY.values()])"
# Should all be: groq
```

### Frequent Switching

**Symptom:** Every request switches models multiple times

**Possible Causes:**

**1. High Traffic on Free Tier**
- ✅ **Expected behavior** during peak times
- Models auto-recover quickly

**2. API Key Issues**
- Verify key is valid
- Check it's not rate-limited elsewhere

**3. Groq Service Degradation**
- Check https://status.groq.com
- Wait for service restoration

---

## Development Issues

### Tests Failing

**Symptom:**
```
FAILED tests/test_council.py::test_run_council_basic
```

**Solutions:**

**1. Install dev dependencies:**
```powershell
cd backend
pip install -r requirements-dev.txt
```

**2. Check environment:**
```powershell
pytest tests/test_council.py -v --tb=short
```

**3. Mock external calls:**
- Tests should mock API calls
- Check `conftest.py` for fixtures

### Import Errors in Tests

**Symptom:**
```
ModuleNotFoundError: No module named 'app'
```

**Solution:**
```powershell
# Run tests from backend directory
cd backend
pytest tests/ -v

# Or set PYTHONPATH
$env:PYTHONPATH="backend"; pytest
```

### Linting Errors

**Symptom:**
```
ruff: error: Command not found
```

**Solution:**
```powershell
pip install ruff
ruff check backend/app
(cd frontend && npm test)
```

---

## Environment-Specific Issues

### Windows-Specific

**PowerShell Script Execution Disabled**

**Symptom:**
```
.\start_all.ps1 : File cannot be loaded because running scripts is disabled
```

**Solution:**
```powershell
# Allow script execution (one-time)
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# Then run script
.\start_all.ps1
```

**Path Issues with Spaces**

**Symptom:**
```
No such file or directory: 'C:/Users/First Last/...'
```

**Solution:**
```powershell
# Use quotes in commands
cd "C:\Users\First Last\AI-Council"
```

### Linux/Mac-Specific

**Permission Denied**

**Symptom:**
```
bash: ./start_all.sh: Permission denied
```

**Solution:**
```bash
cd backend
uvicorn app.main:app --port 8000
```

**Port Already in Use**

**Symptom:**
```
Address already in use
```

**Solution:**
```bash
# Find process
lsof -i :8000

# Kill process
kill -9 <PID>
```

---

## Docker Issues

### Build Fails

**Symptom:**
```
ERROR: failed to solve: process "/bin/sh -c pip install -r requirements.txt" did not complete
```

**Solutions:**

**1. Clear Docker cache:**
```bash
docker compose down
docker system prune -a
docker compose up --build
```

**2. Check Docker version:**
```bash
docker --version  # Should be 20.10+
docker compose version  # Compose v2.24+ (for optional env_file)
```

### Container Won't Start

**Symptom:**
```
backend exited with code 1
```

**Debug:**
```bash
# View logs
docker compose logs backend

# Run interactively
docker compose exec backend sh
```

### Environment Variables Not Loaded

**Symptom:**
```
WARNING: Missing provider API keys
```

**Solution:**
```bash
# Make sure .env file exists
ls -la .env

# Docker Compose automatically loads .env
# Or specify explicitly:
docker compose --env-file .env up
```

---

## Advanced Debugging

### Enable Debug Logging

**In .env:**
```bash
LOG_LEVEL=DEBUG
```

**Restart backend:**
```powershell
# Stop: Ctrl+C
# Start again
.\start_backend.ps1
```

### Check API Health

**Manual test:**
```powershell
# Health endpoint
Invoke-WebRequest http://localhost:8000/v1/health | ConvertFrom-Json

# Should return:
# {
#   "status": "ok",
#   "version": "2.1.0",
#   "providers_missing": []
# }
```

### Test Council Directly

**Python script:**
```python
# test_council.py
import asyncio
from backend.app.council import run_council

async def test():
    result = await run_council("Should I invest in stocks or bonds?")
    print(f"Success: {result.final_answer[:100]}...")

asyncio.run(test())
```

**Run:**
```powershell
python test_council.py
```

### Monitor Network Requests

**Browser DevTools:**
1. Open http://localhost:8000
2. Press F12 (DevTools)
3. Go to the Network tab
4. Convene the council
5. Select the `/v1/ask/stream` request and open **EventStream** to watch each event arrive

---

## Getting Additional Help

### Check Documentation
- **README.md** - Setup, architecture, and feature overview
- **TROUBLESHOOTING.md** - Common setup and runtime issues

### Review Logs
- **Backend**: PowerShell window running backend
- **Browser**: DevTools console (F12) on http://localhost:8000
- **Docker**: `docker compose logs -f`

### Check External Services
- **Groq Status**: https://status.groq.com
- **Python Status**: https://status.python.org

### Debug Checklist

When reporting issues, include:
- [ ] Python version: `python --version`
- [ ] OS and version: `Windows 11`, `macOS 13`, etc.
- [ ] Error message (full traceback)
- [ ] Backend logs (if applicable)
- [ ] Steps to reproduce
- [ ] `.env` configuration (without API key)

---

## Common Error Messages Decoded

| Error | Meaning | Solution |
|-------|---------|----------|
| `ModuleNotFoundError` | Python can't find module | Install dependencies, check directory |
| `Connection refused` | Backend not running | Start backend first |
| `429 Rate limit` | Too many requests | Wait 1 minute or shouldn't happen with auto-switch |
| `401 Unauthorized` | Wrong or missing access key | Enter the API_KEY value under "Access key" |
| `503 Service unavailable` (from /v1/ask) | No council member responded | Check provider keys and status.groq.com |
| `502 Bad Gateway` | Backend error | Check backend logs |
| `503 Service unavailable` | Groq service down | Check status.groq.com |

---

## Still Having Issues?

If problems persist:

1. **Restart everything**: Close all windows, restart
2. **Reinstall dependencies**: Delete `venv`, reinstall
3. **Check file permissions**: Ensure you can read/write
4. **Review code**: Check for any local modifications
5. **Test individually**: check /v1/health first, then the web interface

**Remember:** The system is designed to be resilient. Most issues are configuration or environment-related, not code bugs.

---

**Last Updated:** 2026-09-14  
**Applies to:** AI Council v2.1 with Auto-Switching
