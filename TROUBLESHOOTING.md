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
pip install -r frontend\requirements.txt
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

# Update frontend to use new backend URL in sidebar
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

### Frontend Connection Error

**Symptom:**
```
Connection refused at http://localhost:8000
```

**Solution:**
1. **Check if backend is running**: Visit http://localhost:8000/v1/health
2. **Start backend first**: `.\start_backend.ps1`
3. **Check firewall**: Ensure localhost connections are allowed
4. **Verify port**: Backend should be on port 8000

---

## Runtime Errors

### "All models failed" Error

**Symptom:**
```
Error 502: operator failed after 3 attempts with all available models
```

**Causes & Solutions:**

**1. Invalid API Key**
```powershell
# Check your .env file
cat .env
# Verify GROQ_API_KEY is correct
```

**2. Rate Limits Exceeded (All 5 Models)**
- **Wait 1 minute** - Free tier limits reset quickly
- **Try again** - Limits are per-minute
- **Consider Groq Pro** - Higher limits for production

**3. Groq Service Down**
- Check status: https://status.groq.com
- Wait for service restoration
- Use alternative provider (if configured)

### Rate Limit Error (Should Not Happen)

**Symptom:**
```
Error 429: Rate limit exceeded
```

**This shouldn't happen** with auto-switching enabled!

**If you see this:**
1. Check `GROQ_FALLBACK_CHAIN` in `backend/app/config.py` has all 5 models
2. Verify auto-switching is enabled (not disabled in code)
3. Check backend logs for "auto-switching" messages

**Debug:**
```powershell
# Check config
cd backend
python -c "from app.config import GROQ_FALLBACK_CHAIN; print(GROQ_FALLBACK_CHAIN)"

# Should output 5 models:
# ('openai/gpt-oss-20b', 'openai/gpt-oss-120b', ...)
```

### Prompt Injection Detected

**Symptom:**
```
Error 400: Invalid prompt: potential injection attempt detected
```

**Cause:** Your prompt contains suspicious patterns

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
ATTACHMENT_CACHE_MAXSIZE=25  # Default: 100
```

**3. Limit Concurrent Debate**
```bash
DEBATE_CONCURRENCY_LIMIT=1  # Default: 2
```

---

## Auto-Switching Issues

### Not Seeing ⚡ Indicator

**Symptom:** Models switch but no indicator shows

**Check:**
1. **Backend Response**: `switched_from_model` field should be present
2. **Frontend Version**: Make sure you have latest code
3. **Browser Cache**: Hard refresh (Ctrl+Shift+R)

### Models Not Switching

**Symptom:** Get errors instead of automatic fallback

**Debug Steps:**

**1. Check fallback chain:**
```powershell
cd backend
python -c "from app.config import GROQ_FALLBACK_CHAIN; print('Models:', len(GROQ_FALLBACK_CHAIN))"
# Should print: Models: 5
```

**2. Check error detection:**
```powershell
# Look at backend logs
# Should see: "auto-switching to..." messages
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
ruff check frontend
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
chmod +x start_all.sh start_backend.sh start_frontend.sh
./start_all.sh
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
ERROR: failed to solve with frontend dockerfile
```

**Solutions:**

**1. Clear Docker cache:**
```bash
docker-compose down
docker system prune -a
docker-compose up --build
```

**2. Check Docker version:**
```bash
docker --version  # Should be 20.10+
docker-compose --version  # Should be 2.0+
```

### Container Won't Start

**Symptom:**
```
backend exited with code 1
```

**Debug:**
```bash
# View logs
docker-compose logs backend

# Run interactively
docker-compose run backend bash
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
docker-compose --env-file .env up
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
#   "version": "1.0.0",
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
1. Open frontend (http://localhost:8501)
2. Press F12 (DevTools)
3. Go to Network tab
4. Submit a question
5. Check requests to `/v1/ask`

---

## Getting Additional Help

### Check Documentation
- **README.md** - Setup, architecture, and feature overview
- **TROUBLESHOOTING.md** - Common setup and runtime issues

### Review Logs
- **Backend**: PowerShell window running backend
- **Frontend**: PowerShell window running frontend
- **Docker**: `docker-compose logs -f`

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
| `401 Unauthorized` | Invalid API key | Check GROQ_API_KEY in .env |
| `413 Payload too large` | File too big | Reduce file size (<12MB) |
| `502 Bad Gateway` | Backend error | Check backend logs |
| `503 Service unavailable` | Groq service down | Check status.groq.com |

---

## Still Having Issues?

If problems persist:

1. **Restart everything**: Close all windows, restart
2. **Reinstall dependencies**: Delete `venv`, reinstall
3. **Check file permissions**: Ensure you can read/write
4. **Review code**: Check for any local modifications
5. **Test individually**: Test backend, then frontend separately

**Remember:** The system is designed to be resilient. Most issues are configuration or environment-related, not code bugs.

---

**Last Updated:** 2026-08-25  
**Applies to:** AI Council v2.1 with Auto-Switching
