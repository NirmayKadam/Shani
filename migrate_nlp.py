import os
import shutil

src_dir = r"c:\Users\Siddharth\Desktop\CODING\CAPSTONE SEM6-7\MarketSentimentAnalysis-ADM-MLDL-\MarketSentimentAnalysis2\app\domain\nlp_logic"
dest_dir = r"c:\Users\Siddharth\Desktop\CODING\CAPSTONE SEM6-7\MarketSentimentAnalysis-ADM-MLDL-\MarketSentimentAnalysis2\domains\analytics\application\nlp"

# We want to move all contents (recursively) to the target directory.
# Then replace "app.domain.nlp_logic" with "domains.analytics.application.nlp", etc.

def run():
    for root, _, files in os.walk(src_dir):
        for f in files:
            if not f.endswith(".py"):
                continue
            src_path = os.path.join(root, f)
            dest_file_name = f
            dest_path = os.path.join(dest_dir, dest_file_name)

            if f == "__init__.py":
                continue # we don't necessarily want all the inits, but let's skip them

            with open(src_path, "r", encoding="utf-8") as file:
                content = file.read()
            
            # replacements mapping
            replacements = {
                "app.domain.nlp_logic.domain.finbert_engine": "domains.analytics.application.nlp.finbert_engine",
                "app.domain.nlp_logic.domain.analyzer": "domains.analytics.application.nlp.analyzer",
                "app.domain.nlp_logic.domain.timeframes": "domains.analytics.application.nlp.timeframes",
                "app.domain.nlp_logic.domain.model": "domains.analytics.application.nlp.model",
                "app.domain.nlp_logic.domain.events": "domains.analytics.application.nlp.events",
                "app.domain.nlp_logic.application.inference": "domains.analytics.application.nlp.inference",
                "app.domain.nlp_logic": "domains.analytics.application.nlp"
            }
            
            for old, new in replacements.items():
                content = content.replace(old, new)

            # Special case for SentimentOrchestrator / event_subscriber mapping
            if f == "event_subscriber.py":
                dest_path = os.path.join(dest_dir, "SentimentOrchestrator.py")
                # rewrite class based or keep as module?
                # we'll keep as module but name the file SentimentOrchestrator.py
            
            if f == "finbert_scorer.py":
                dest_path = os.path.join(dest_dir, "FinBertScorer.py")

            with open(dest_path, "w", encoding="utf-8") as file:
                file.write(content)
            
            print(f"Migrated {f} -> {os.path.basename(dest_path)}")

if __name__ == "__main__":
    run()
