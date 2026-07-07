@echo off
set HTTP_PROXY=http://127.0.0.1:7890
set HTTPS_PROXY=http://127.0.0.1:7890
set OPENAI_API_KEY=sk-ad586317d4534bf1a7f458c821212a4a
set OPENAI_BASE_URL=https://api.deepseek.com
set PYTHONIOENCODING=utf-8

if "%1"=="" (
    set /p TICKER=Stock Code (e.g. 600519.SS / 000001.SZ): 
) else (
    set TICKER=%1
)

py -3.13 -m tradingagents cli --ticker %TICKER% --llm_provider openai --deep_think_llm deepseek-chat --quick_think_llm deepseek-chat --max_debate_rounds 1 --max_risk_discuss_rounds 1 --response_language zh-CN

pause
