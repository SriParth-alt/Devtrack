import json
import os
import threading
from functools import partial

from django.conf import settings
from django.http import JsonResponse as _JsonResponse
from django.views.decorators.csrf import csrf_exempt

from issues.models import Issue, Reporter, build_issue

# Keep characters like the em dash readable in raw responses.
JsonResponse = partial(_JsonResponse, json_dumps_params={'ensure_ascii': False})

ISSUES_FILE = os.path.join(settings.BASE_DIR, 'issues.json')
REPORTERS_FILE = os.path.join(settings.BASE_DIR, 'reporters.json')

# Serialises read-modify-write cycles so concurrent POSTs in the dev server
# don't overwrite each other's records.
_file_lock = threading.Lock()


# ---------- JSON file helpers ----------

def read_json(path):
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read().strip()
        return json.loads(content) if content else []


def write_json(path, records):
    tmp_path = path + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, path)  # atomic swap: never leaves a half-written file


def parse_body(request):
    """Return (data, error_response)."""
    try:
        data = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return None, JsonResponse({'error': 'Request body must be valid JSON'}, status=400)
    if not isinstance(data, dict):
        return None, JsonResponse({'error': 'Request body must be a JSON object'}, status=400)
    return data, None


def parse_id(raw):
    """Return (int_id, error_response)."""
    try:
        return int(raw), None
    except (TypeError, ValueError):
        return None, JsonResponse({'error': 'id must be an integer'}, status=400)


def next_id(records):
    return max((r['id'] for r in records), default=0) + 1


def method_not_allowed():
    return JsonResponse({'error': 'Method not allowed'}, status=405)


# ---------- Reporters ----------

@csrf_exempt
def reporters(request):
    if request.method == 'GET':
        return get_reporters(request)
    if request.method == 'POST':
        return create_reporter(request)
    return method_not_allowed()


def get_reporters(request):
    all_reporters = read_json(REPORTERS_FILE)
    raw_id = request.GET.get('id')

    if raw_id is None:
        return JsonResponse(all_reporters, safe=False, status=200)

    reporter_id, err = parse_id(raw_id)
    if err:
        return err
    for reporter in all_reporters:
        if reporter['id'] == reporter_id:
            return JsonResponse(reporter, status=200)
    return JsonResponse({'error': 'Reporter not found'}, status=404)


def create_reporter(request):
    data, err = parse_body(request)
    if err:
        return err

    with _file_lock:
        all_reporters = read_json(REPORTERS_FILE)
        reporter = Reporter(
            id=data.get('id', next_id(all_reporters)),
            name=data.get('name'),
            email=data.get('email'),
            team=data.get('team'),
        )
        try:
            reporter.validate()
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)

        if any(r['id'] == reporter.id for r in all_reporters):
            return JsonResponse(
                {'error': f'Reporter with id {reporter.id} already exists'}, status=400
            )

        all_reporters.append(reporter.to_dict())
        write_json(REPORTERS_FILE, all_reporters)

    return JsonResponse(reporter.to_dict(), status=201)


# ---------- Issues ----------

@csrf_exempt
def issues(request):
    if request.method == 'GET':
        return get_issues(request)
    if request.method == 'POST':
        return create_issue(request)
    return method_not_allowed()


def get_issues(request):
    all_issues = read_json(ISSUES_FILE)
    raw_id = request.GET.get('id')
    status_filter = request.GET.get('status')

    if raw_id is not None:
        issue_id, err = parse_id(raw_id)
        if err:
            return err
        for issue in all_issues:
            if issue['id'] == issue_id:
                return JsonResponse(issue, status=200)
        return JsonResponse({'error': 'Issue not found'}, status=404)

    if status_filter is not None:
        if status_filter not in Issue.ALLOWED_STATUSES:
            return JsonResponse(
                {'error': f"Invalid status. Allowed values: {', '.join(Issue.ALLOWED_STATUSES)}"},
                status=400,
            )
        filtered = [i for i in all_issues if i['status'] == status_filter]
        return JsonResponse(filtered, safe=False, status=200)

    return JsonResponse(all_issues, safe=False, status=200)


def create_issue(request):
    data, err = parse_body(request)
    if err:
        return err

    with _file_lock:
        all_issues = read_json(ISSUES_FILE)

        # Subclass chosen by priority: critical -> CriticalIssue,
        # low -> LowPriorityIssue, medium/high -> Issue.
        issue = build_issue(
            id=data.get('id', next_id(all_issues)),
            title=data.get('title'),
            description=data.get('description', ''),
            status=data.get('status', 'open'),
            priority=data.get('priority'),
            reporter_id=data.get('reporter_id'),
        )
        try:
            issue.validate()
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)

        if any(i['id'] == issue.id for i in all_issues):
            return JsonResponse(
                {'error': f'Issue with id {issue.id} already exists'}, status=400
            )

        # Enforce the 1:many relationship: the reporter must exist.
        if not any(r['id'] == issue.reporter_id for r in read_json(REPORTERS_FILE)):
            return JsonResponse(
                {'error': f'Reporter with id {issue.reporter_id} does not exist'}, status=400
            )

        all_issues.append(issue.to_dict())
        write_json(ISSUES_FILE, all_issues)

    response_data = issue.to_dict()
    response_data['message'] = issue.describe()
    return JsonResponse(response_data, status=201)
