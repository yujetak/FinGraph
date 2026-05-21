import os
import subprocess
import sys

# 프로젝트 루트 디렉토리를 Python 경로에 추가하여 ModuleNotFoundError 방지
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))


def run_command(cmd):
    print("\n========================================")
    print(f"Running: {cmd}")
    print("========================================\n")
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    result = subprocess.run(cmd, shell=True, env=env)
    if result.returncode != 0:
        print(f"Command failed with exit code {result.returncode}: {cmd}")
        sys.exit(result.returncode)


if __name__ == "__main__":
    print("Starting background rebuilding pipeline...")
    # 1. 크롤링 (finScrapping.py)
    run_command(r".\.venv\Scripts\python.exe src/graphBuilder/scrapping/finScrapping.py")
    
    # 2. 지식 그래프 빌드 (finGraph.py)
    run_command(r".\.venv\Scripts\python.exe src/graphBuilder/neo4j/finGraph.py")
    
    print("\n[OK] Background rebuilding pipeline completed successfully!")
