:: parse any leftover log from a previous run before the server overwrites it
python token_stats\parse_token_stats.py token_stats\raw_server.log token_stats\parsed_request_stats.md --delete

llama.cpp-CUDA\llama-server.exe ^
  --port 8000 ^
  --models-preset models.ini ^
  --timeout 600 ^
  --models-max 1 ^
  --parallel 1 ^
  --load-mode dio ^
  --log-colors off ^
  --log-file token_stats/raw_server.log

:: parse the last run's log into the stats table, then delete the log
python token_stats\parse_token_stats.py token_stats\raw_server.log token_stats\parsed_request_stats.md --delete