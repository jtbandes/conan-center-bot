import re
import json
import datetime
import logging
import aiohttp

from . import __version__
from .github import get_github_token
from .utils import format_duration


ISSUE_URL_RE = re.compile(r"github.com/([^/]+)/([^/]+)/issues/([0-9]+)")
logger = logging.getLogger(__name__)


async def _update_issue(issue_url, content):
    match = ISSUE_URL_RE.search(issue_url)
    if not match:
        logger.error("update failed: bad issue URL")
        return False

    owner, repo, issue_number = match.groups()
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}"
    github_token = get_github_token()
    headers = {"Accept": "application/vnd.github.v3+json"}
    if github_token:
        headers["Authorization"] = f"token {github_token}"
    data = {"body": content}

    async with aiohttp.ClientSession() as client:
        async with client.patch(url, json=data, headers=headers) as resp:
            if resp.ok:
                return True

            logger.error("update failed: %s", resp.reason)
            return False


async def update_status_issue(  # pylint: disable=too-many-locals
    update_status_path,
    issue_url_list,
    no_link_pr,
):
    with open(update_status_path) as f:
        update_status = json.load(f)

    def make_pr_text(recipe):
        if recipe["prs_opened"]:
            if no_link_pr:
                return ", ".join([f"# {pr['number']}" for pr in recipe["prs_opened"]])
            else:
                return ", ".join(
                    [f"[#{pr['number']}]({pr['url']})" for pr in recipe["prs_opened"]]
                )

        branch = recipe["updated_branch"]
        owner, repo, branch_name = branch["owner"], branch["repo"], branch["branch"]
        if not (owner and repo and branch_name):
            return "No"

        return f"[Open one](https://github.com/{owner}/{repo}/pull/new/{branch_name})"

    def str_to_pre(err):
        return "<pre>" + err.replace("\n", "<br/>") + "</pre>"

    date = datetime.datetime.fromisoformat(update_status["date"]).strftime("%d/%m/%Y")
    recipes = update_status["recipes"]
    up_to_date = [r for r in recipes if r["up_to_date"]]
    updatable = [r for r in recipes if r["updatable"]]
    inconsistent_version = [r for r in recipes if r["inconsistent_versioning"]]
    unsupported = [r for r in recipes if not r["supported"]]

    text = "\n".join(
        [
            "# Conan Center Bot",
            "",
            f"* Date: {date}",
            f"* Parsed recipes: {len(recipes)}",
            f"* Up-to-date recipes: {len(up_to_date)}",
            f"* Updatable recipes: {len(updatable)}",
            f"* Inconsistent recipes: {len(inconsistent_version)}",
            f"* Unsupported recipes: {len(unsupported)}",
            f"* Duration: {format_duration(update_status['duration'])}",
            f"* Version: {update_status['ccb_version']}",
            "",
            "Find more details in the [GitHub Pages](https://qchateau.github.io/conan-center-bot/).",
            ""
            "This list is auto-generated by [Conan Center Bot](https://github.com/qchateau/conan-center-bot) "
            "and the updatability detection or version parsing can be flawed. Any help improving "
            "this tool is welcome !",
            "",
            "You can also use [Conan Center Bot](https://github.com/qchateau/conan-center-bot) "
            "to automatically generate an update for a recipe.",
            "",
            "### Updatable recipes" "",
            "|Name|Recipe version|New version|Upstream version|Pull request|",
            "|----|--------------|-----------|----------------|------------|",
        ]
        + [
            "|".join(
                [
                    "",
                    f"[{r['name']}]({r['homepage']})",
                    f"{r['recipe_version']}",
                    f"{r['upstream_version']}",
                    f"{r['upstream_tag']}",
                    make_pr_text(r),
                    "",
                ]
            )
            for r in updatable
        ]
        + [
            "",
            "### Inconsistent recipes",
            "",
            "The following recipes are not consistent with their upstream versioning scheme. "
            "Most of the times it means the current recipe version is not related to any upstream tag.",
            "",
            "|Name|Current recipe version|Upstream version|",
            "|----|----------------------|----------------|",
        ]
        + [
            "|".join(
                [
                    "",
                    f"[{r['name']}]({r['homepage']})",
                    f"{r['recipe_version']}",
                    f"{r['upstream_tag']}",
                    "",
                ]
            )
            for r in inconsistent_version
        ]
        + [
            "",
            "### Updatable recipes with errors",
            "",
            "The following recipes are detected as updatable but the bot "
            "failed to automatically update the recipe."
            "",
            "<table>",
            "<tr><th>Name</th><th>Error</th></tr>",
        ]
        + [
            "<tr><td>"
            + f"<a href=\"{r['homepage']}\">{r['name']}</a>"
            + "</td>"
            + "<td>"
            + f"{str_to_pre(r['update_error'])}"
            + "</td>"
            + "</tr>"
            for r in updatable
            if r["update_error"] is not None
        ]
    )

    if issue_url_list:
        ok = True
        for issue_url in issue_url_list:
            this_ok = await _update_issue(issue_url, text)
            if this_ok:
                logger.info("updated: %s", issue_url)
            else:
                logger.error("error while updating: %s", issue_url)
            ok = ok and this_ok
    else:
        print(text)
        ok = True

    return 0 if ok else 1
