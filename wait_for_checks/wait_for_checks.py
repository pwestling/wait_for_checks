# type: ignore
import math
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Thread
from urllib.parse import urlparse

import os

import requests

CHECK = "\u2705"
X = "\u274C"
PROCESSING = ["|", "/", "\u2015", "\\", "|", "/", "-", "\\"]

query = """
{{
  node(
    id: "{}"
  ) {{

    ... on Commit {{
       checkSuites(first: 100) {{
      edges {{
        node {{
          workflowRun {{
            workflow {{
              name
            }}
          }}
          status
          checkRuns(first: 100) {{
            edges {{
              node {{
                name
                status
                conclusion
              }}
            }}
          }}
        }}
      }}
    }}
    }}
  }}
}}
"""

def main():
    token = os.getenv("GITHUB_TOKEN")

    target = sys.argv[1]
    parsed_target = urlparse(target)
    path_parts = parsed_target.path.split("/")
    user_or_org = path_parts[1]
    repo_name = path_parts[2]
    kind = lambda: path_parts[3]
    pr_number_or_commit_sha = lambda: path_parts[4]

    def github(endpoint: str) -> dict:
        response = requests.get(
            f"https://api.github.com{endpoint}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
        )
        return response.json()

    def githubgql(query: str) -> dict:
        response = requests.post(
            "https://api.github.com/graphql",
            json={"query": query},
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
        )
        return response.json()

    if len(path_parts) == 3:
        pr = github(f"/repos/{user_or_org}/{repo_name}/branches/master")
        head_commit = pr["commit"]["sha"]
    elif kind() == "pull":
        pr: dict = github(f"/repos/{user_or_org}/{repo_name}/pulls/{pr_number_or_commit_sha()}")
        head_commit = pr["head"]["sha"]
    else:
        head_commit = pr_number_or_commit_sha()
    print(f"Waiting for checks to complete for commit {head_commit}...")
    commit_node = github(f"/repos/{user_or_org}/{repo_name}/commits/{head_commit}")["node_id"]

    def get_status_symbol(status: str, tick: int) -> str:
        if status.lower() == "success":
            return CHECK
        elif status.lower() == "failure":
            return X
        elif status.lower() == "in_progress" or status.lower() == "queued":
            return PROCESSING[tick % len(PROCESSING)]
        else:
            return status

    def clear_terminal_lines(n: int) -> None:
        for _ in range(n):
            sys.stdout.write("\033[F")

    with ThreadPoolExecutor() as executor:
        runs_box = {"results": {}}


        def check_status():
            while True:
                results = githubgql(query.format(commit_node))
                runs_box["results"] = results
                time.sleep(5)

        t = Thread(target=check_status, daemon=True)
        t.start()

        def truncate(width:int, name:str) -> str:
            if len(name) > width:
                return name[:width-3] + "..."
            else:
                return name

        workflow_name_width = 40
        job_name_width = 60

        def get_status(workflow: dict) -> str:
            job_nodes = [node["node"] for node in workflow["checkRuns"]["edges"]]
            if all((node["status"] == "COMPLETED" and (node["conclusion"] == "SUCCESS" or node["conclusion"] == "NEUTRAL")) for node in job_nodes):
                return "SUCCESS"
            if any((node["status"] == "COMPLETED" and node["conclusion"] == "FAILURE") for node in job_nodes):
                return "FAILURE"
            if all((node["status"] == "COMPLETED" for node in job_nodes)):
                raise Exception("All jobs completed but status unknown: {}".format(job_nodes))
            return "IN_PROGRESS"
        def render():
            tick = 0
            printed_lines = 0
            print(
                "\033[1m{:{width}}{:{width2}}{:5}\033[0m".format(
                    "Workflow", "Running Jobs", "Status", width=workflow_name_width, width2=job_name_width
                )
            )
            while True:
                clear_terminal_lines(printed_lines)
                printed_lines = 0
                results = runs_box["results"]
                if "data" in results:
                    workflows = [run["node"] for run in results["data"]["node"]["checkSuites"]["edges"] if (run["node"]["workflowRun"])]
                    workflows = [workflow for workflow in workflows if workflow["workflowRun"]["workflow"]["name"] != "workflow_metrics"]
                    workflows = sorted(workflows, key=lambda workflow: workflow["workflowRun"]["workflow"]["name"])
                    for workflow in workflows:

                        workflow_name = truncate(workflow_name_width, workflow["workflowRun"]["workflow"]["name"])
                        status = get_status(workflow)
                        status_symbol = get_status_symbol(status, math.floor(tick/10))
                        jobs = [node["node"]["name"] for node in workflow["checkRuns"]["edges"] if node["node"]["status"].lower() == "in_progress"]
                        job_name = truncate(job_name_width, ",".join(jobs))
                        print(
                            "{:{width}}{:{width2}}{}".format(
                                workflow_name, job_name, status_symbol, width=workflow_name_width, width2=job_name_width
                            )
                        )
                        printed_lines += 1
                    statuses = [workflow["status"].lower() for workflow in workflows]
                    if len(statuses) > 0:
                        if all(status == "completed" for status in statuses):
                            print("All workflows completed.")
                            return True
                        if any(status == "failed" for status in statuses):
                            print("One or more workflows failed.")
                            return False
                time.sleep(0.05)
                tick += 1

        result = render()
        if not result:
            sys.exit(1)


if __name__ == '__main__':
    main()
