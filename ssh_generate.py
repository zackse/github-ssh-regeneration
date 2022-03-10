#! /usr/bin/env python3

import sys
import json
import typing
import urllib.error
import urllib.parse
import urllib.request
from email.message import Message

# This script will check if a repo has a CircleCI checkout key
# If the key is ssh-rsa, it will log old key and add a new key
# This new key will be ssh-ed25519 and become the prefered key

class Response(typing.NamedTuple):
    body: str
    headers: Message
    status: int
    error_count: int = 0

    def json(self) -> typing.Any:
        """
        Decode body's JSON.

        Returns:
            Pythonic representation of the JSON object
        """
        try:
            output = json.loads(self.body)
        except json.JSONDecodeError:
            output = ""
        return output


def request(
    url: str,
    data: dict = None,
    params: dict = None,
    headers: dict = None,
    method: str = "GET",
    data_as_json: bool = True,
    error_count: int = 0,
) -> Response:
    if not url.casefold().startswith("http"):
        raise urllib.error.URLError("Incorrect and possibly insecure protocol in url")
    method = method.upper()
    request_data = None
    headers = headers or {}
    data = data or {}
    params = params or {}
    headers = {"Accept": "application/json", **headers}

    if method == "GET":
        params = {**params, **data}
        data = None

    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True, safe="/")

    if data:
        if data_as_json:
            request_data = json.dumps(data).encode()
            headers["Content-Type"] = "application/json; charset=UTF-8"
        else:
            request_data = urllib.parse.urlencode(data).encode()

    httprequest = urllib.request.Request(
        url, data=request_data, headers=headers, method=method
    )

    try:
        with urllib.request.urlopen(httprequest) as httpresponse:
            response = Response(
                headers=httpresponse.headers,
                status=httpresponse.status,
                body=httpresponse.read().decode(
                    httpresponse.headers.get_content_charset("utf-8")
                ),
            )
    except urllib.error.HTTPError as e:
        response = Response(
            body=str(e.reason),
            headers=e.headers,
            status=e.code,
            error_count=error_count + 1,
        )

    return response


def convert_vcs(vcs_input):
    vcs_map = {
        "gh": "github",
        "bb": "bitbucket",
        "github": "github",
        "bitbucket": "bitbucket",
    }

    if vcs_input in vcs_map:
        return vcs_map[vcs_input]
    raise Exception("invalid vcs provided: " + vcs_input)


def main():
    # Set to personal API token
    CIRCLE_API_TOKEN = sys.argv[1]

    # Set to organization
    ORG = sys.argv[2]

    # Set to github or bitbucket
    VCS = convert_vcs(sys.argv[3])

    headers = {'Circle-Token': CIRCLE_API_TOKEN, 'Content-type': 'application/json'}

    # /organization isn't documented?
    projects_url = "https://circleci.com/api/v1.1/projects"
    projects_resp = request(url=projects_url, headers=headers)
    if projects_resp.error_count > 0:
        raise Exception("error retrieving projects: {response} url: {url}".format(response=str(projects_resp), url=projects_url))

    projects_resp = projects_resp.json()

    project_names = []
    for project in projects_resp:
        project_name = project['reponame']
        vcs_url = project['vcs_url']
        vcs_url_parts = vcs_url.split("/")
        project_name = vcs_url_parts[-1]
        org_name = vcs_url_parts[-2]

        project_names.append(project_name)

    for project in project_names:
        print(f"examining {project}")
        # Pulls all checkout keys for a project
        ssh_keys_url = "https://circleci.com/api/v2/project/{vcs}/{org}/{project}/checkout-key".format(vcs=VCS, org=ORG, project=project)
        ssh_keys_resp = request(url=ssh_keys_url, headers=headers)
        if ssh_keys_resp.error_count > 0:
            raise Exception("error getting ssh_keys: {response} url: {url}".format(response=str(ssh_keys_resp), url=ssh_keys_url))

        ssh_keys_resp = ssh_keys_resp.json()

        key_info = ssh_keys_resp['items']
        if len(key_info) == 0:
            print("  no keys found, skipping")
            continue

        # Finds the current prefered key, which is used with checkout step
        # Checks if the prefered key is ssh-rsa
        key_info = key_info[0]
        if key_info['preferred'] and key_info['public_key'].startswith('ssh-rsa'):
            print(f'found key {key_info}')
        else:
            print("{project} prefered key is not ssh-rsa, no action taken.".format(project=project))

if __name__ == '__main__':
    main()
