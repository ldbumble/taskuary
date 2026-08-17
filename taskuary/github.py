"""Minimal GitHub helpers (optional): a fine-grained PAT is all the config."""
import requests

GH = 'https://api.github.com'
def _h(tok): return {'Authorization': f'Bearer {tok}', 'Accept': 'application/vnd.github+json',
                     'X-GitHub-Api-Version': '2022-11-28'}

def create_issue(tok, repo, title, body):
    r = requests.post(f'{GH}/repos/{repo}/issues', headers=_h(tok), json={'title': title, 'body': body}, timeout=20)
    r.raise_for_status()
    j = r.json()
    return {'number': j['number'], 'url': j['html_url']}

def close_issue(tok, repo, number, comment=None):
    if comment:
        requests.post(f'{GH}/repos/{repo}/issues/{number}/comments', headers=_h(tok), json={'body': comment}, timeout=20).raise_for_status()
    requests.patch(f'{GH}/repos/{repo}/issues/{number}', headers=_h(tok), json={'state': 'closed'}, timeout=20).raise_for_status()

def list_accessible_repos(tok):
    r = requests.get(f'{GH}/user/repos', headers=_h(tok), params={'per_page': 100, 'sort': 'pushed'}, timeout=20)
    r.raise_for_status()
    return [{'full_name': x['full_name'], 'description': x.get('description'), 'archived': x.get('archived')}
            for x in r.json()]
