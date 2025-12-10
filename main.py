from modules.pdf_extraction import list_projects
from pipeline.run_pipeline import run_pipeline
import warnings
warnings.filterwarnings("ignore")


if __name__ == "__main__":
    project = list_projects()[0]  # take first folder only
    run_pipeline(project)
