# type: ignore
import math
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from threading import Thread
from typing import Iterable, Generator, Tuple
from urllib.parse import urlparse

from github import Github
import os

from github.CheckRun import CheckRun
from github.PaginatedList import PaginatedList
from github.PullRequest import PullRequest
from github.Repository import Repository
from github.Workflow import Workflow
from github.WorkflowRun import WorkflowRun
import curses
import requests
import json
import concurrent.futures

CHECK = "\u2705"
X = "\u274C"
PROCESSING = ["|", "/", "\u2015", "\\", "|", "/", "-", "\\"]



def main():
    token = os.getenv("GITHUB_TOKEN")

    gh = Github(token)

    target = sys.argv[1]
    parsed_target = urlparse(target)
    path_parts = parsed_target.path.split("/")
    user_or_org = path_parts[1]
    repo_name = path_parts[2]
    kind = path_parts[3]
    pr_number_or_commit_sha = path_parts[4]

    def github(endpoint: str) -> dict:
        response = requests.get(
            f"https://api.github.com{endpoint}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
        ).json()

    def githubgql(query: str) -> dict:
        response = requests.post(
            "https://api.github.com/graphql",
            data=query,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
        ).json()

    repo: Repository = gh.get_repo(f"{user_or_org}/{repo_name}")
    if kind == "pull":
        pr: PullRequest = repo.get_pull(int(pr_number_or_commit_sha))
        head_commit = pr.head.ref
    else:
        head_commit = pr_number_or_commit_sha

    commit_node = github(f"/repos/{user_or_org}/{repo}/commits/{head_commit}")["node_id"]

    check_runs = list(repo.get_commit(head_commit).get_check_runs())

    def get_workflow_for_check(check_run: CheckRun) -> dict:
        # The Actions job ID is the same as the Checks run ID
        # (not to be confused with the Actions run ID).
        response = github(f"/repos/{user_or_org}/{repo_name}/actions/jobs/{check_run.id}")
        return response

    def get_status_symbol(status: str, tick: int) -> str:
        if status == "completed":
            return CHECK
        elif status == "failed":
            return X
        elif status == "in_progress":
            return PROCESSING[tick % len(PROCESSING)]
        else:
            return status

    def clear_terminal_lines(n: int) -> None:
        for _ in range(n):
            sys.stdout.write("\033[F")

    with ThreadPoolExecutor() as executor:
        workflow_jobs = executor.map(get_workflow_for_check, check_runs)
        workflow_run_ids = {wr["run_id"] for wr in workflow_jobs}

        def get_workflow_run_by_id(run_id: str) -> WorkflowRun:
            return repo.get_workflow_run(run_id)

        def get_workflow_for_run(run: WorkflowRun) -> Workflow:
            return repo.get_workflow(str(run.workflow_id))

        runs = list(executor.map(get_workflow_run_by_id, workflow_run_ids))
        workflows = list(executor.map(get_workflow_for_run, runs))
        print("Waiting for {} workflows for commit {}...".format(len([w for w in workflows if w.name != "workflow_metrics"]), head_commit))

        workflows_by_id = {w.id: w for w in workflows}

        workflows_by_run_id = {run.id: workflows_by_id[run.workflow_id] for run in runs}
        name_length = max([len(w.name) for w in workflows]) + 4

        runs_box = {"runs": runs, "job_names": {}}
        num_runs = len(runs)

        def get_an_in_progress_job_name(run: WorkflowRun) -> Tuple[int, str]:
            jobs_json = requests.get(run.jobs_url, headers={"Authorization": f"Bearer {token}",  "Accept": "application/vnd.github+json",}).json()
            for job in jobs_json["jobs"]:
                if job["status"] == "in_progress":
                    return run.id, job["name"]
            return run.id, ""

        def check_status():
            while True:
                runs = list(executor.map(get_workflow_run_by_id, workflow_run_ids))
                runs_and_job_names = list(executor.map(get_an_in_progress_job_name, runs))
                job_names = {run_id: job_name for (run_id, job_name) in runs_and_job_names}
                runs_box["runs"] = runs
                runs_box["job_names"] = job_names
                time.sleep(5)

        t = Thread(target=check_status, daemon=True)
        t.start()

        def render():
            tick = 0
            printed_lines = 0
            while True:
                clear_terminal_lines(printed_lines)
                printed_lines = 0
                runs, job_names = runs_box["runs"], runs_box["job_names"]
                for run in runs:
                    workflow_name = workflows_by_run_id[run.id].name
                    status_symbol = get_status_symbol(run.status, math.floor(tick/10))
                    job_name = job_names.get(run.id, "") or ""
                    if workflow_name != "workflow_metrics":
                        try:
                            print(
                                "{:{width}}{:{width2}}{}".format(
                                    workflow_name, job_name, status_symbol, width=name_length + 4, width2=name_length+4
                                )
                            )
                        except Exception as e:
                            print(workflow_name, job_name, status_symbol)
                            raise e
                        printed_lines += 1
                    statuses = [run.status for run in runs]
                    if len(statuses) == num_runs:
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


if __name__ == "__main__":
    main()
