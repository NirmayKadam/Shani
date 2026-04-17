import os
import shutil

src_dir = r"c:\Users\Siddharth\Desktop\CODING\CAPSTONE SEM6-7\MarketSentimentAnalysis-ADM-MLDL-\MarketSentimentAnalysis2\app\domain\frontend_api"
dest_dir = r"c:\Users\Siddharth\Desktop\CODING\CAPSTONE SEM6-7\MarketSentimentAnalysis-ADM-MLDL-\MarketSentimentAnalysis2\domains\analytics\api"

def run():
    for root, _, files in os.walk(src_dir):
        for f in files:
            if not f.endswith(".py"):
                continue
            src_path = os.path.join(root, f)

            with open(src_path, "r", encoding="utf-8") as file:
                content = file.read()
            
            replacements = {
                "app.domain.frontend_api.application.services.analysis_service": "domains.analytics.api.analysis_service",
                "app.domain.frontend_api.interfaces.schemas": "domains.analytics.api.schemas",
                "app.domain.frontend_api.domain.read_models": "domains.analytics.api.read_models",
                "app.domain.frontend_api": "domains.analytics.api",
                "app.domain.api.routers": "domains.analytics.api"
            }
            
            for old, new in replacements.items():
                content = content.replace(old, new)

            dest_file_name = f
            # mapping names
            if f == "analyze.py":
                dest_file_name = "SentimentRouter.py"
            elif f == "websocket.py":
                dest_file_name = "EventsRouter.py"
            elif f == "symbols.py":
                dest_file_name = "SymbolsRouter.py"

            dest_path = os.path.join(dest_dir, dest_file_name)

            if f == "__init__.py":
                continue 

            with open(dest_path, "w", encoding="utf-8") as file:
                file.write(content)
            
            print(f"Migrated {f} -> {os.path.basename(dest_path)}")

if __name__ == "__main__":
    run()
