"""Free, source-bounded input review. Does not generate a brief or touch payments."""
import re
import unicodedata
from urllib.parse import urlsplit

from .generator import InputError, normalize_request, request_hash


def _text_key(value):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', value)).strip().casefold()


def review_request(data):
    """Return actionable structural checks, never a paid brief or fact verification.

    Warnings do not silently forbid purchases. Only invalid input is blocking;
    the same normalization contract is used by order creation and generation.
    """
    disclosure = ('This free review checks only supplied input structure and attribution. '
                  'It does not verify facts, detect semantic contradictions, generate a brief, create an order, or initiate payment.')
    checks = []

    def add(code, status, message, fields, question=None):
        checks.append({'code': code, 'status': status, 'message': message,
                       'fields': fields, 'question': question})

    try:
        request = normalize_request(data)
    except InputError as exc:
        add('INPUT_SCHEMA', 'blocking', str(exc), ['request'], 'Correct the input before creating an order.')
        return {'version': 1, 'mode': 'preflight', 'inputValid': False, 'canCreateOrder': False,
                'assessment': 'needs-input', 'checks': checks, 'warningCount': 0,
                'blockingCount': 1, 'questions': [checks[0]['question']], 'counts': {},
                'briefGenerated': False, 'orderCreated': False, 'paymentInitiated': False,
                'disclosure': disclosure}

    add('INPUT_SCHEMA', 'pass', 'Required fields and input bounds match the order contract.', ['title', 'audience', 'objective'])
    for field, label, question in [
        ('deliverables', 'A scoped deliverable list', 'Which files or assets should the owner approve?'),
        ('constraints', 'Delivery constraints', 'What budget, timing, tone, or review constraints apply?'),
        ('facts', 'Supporting facts', 'Which supplied facts support the project objective?'),
    ]:
        present = bool(request[field])
        add(field.upper(), 'pass' if present else 'warning',
            f'{label} supplied.' if present else f'{label} missing; the paid brief will leave an open decision.',
            [field], None if present else question)

    source_gaps = []
    placeholders = {'tbd', 'todo', 'unknown', 'n/a', 'source', '待补充', '未知', '未提供'}
    for index, fact in enumerate(request['facts']):
        source = fact['source']
        placeholder = not source or _text_key(source) in placeholders
        malformed_url = False
        if source.lower().startswith(('http:', 'https:')):
            try:
                parsed = urlsplit(source)
                malformed_url = not parsed.netloc or bool(parsed.username or parsed.password)
            except ValueError:
                malformed_url = True
        if placeholder or malformed_url:
            source_gaps.append(f'facts[{index}].source')
    if not request['facts']:
        add('ATTRIBUTION', 'warning', 'There are no facts to attribute.', ['facts'],
            'Supply facts and identify their source before making factual claims.')
    else:
        add('ATTRIBUTION', 'warning' if source_gaps else 'pass',
            f'{len(source_gaps)} fact source fields are missing, placeholders, malformed URLs, or credential-bearing URLs.' if source_gaps
            else 'Each fact has an attribution label; the label is not proof of accuracy.',
            source_gaps or ['facts'], 'Replace incomplete attribution with an owner-readable source.' if source_gaps else None)

    groups = {}
    for index, fact in enumerate(request['facts']):
        groups.setdefault(_text_key(fact['text']), []).append(index)
    duplicate_groups = [indices for indices in groups.values() if len(indices) > 1]
    duplicate_fields = [f'facts[{index}].text' for indices in duplicate_groups for index in indices]
    add('DUPLICATE_FACTS', 'warning' if duplicate_groups else 'pass',
        f'{len(duplicate_groups)} repeated statements should be consolidated or reviewed; repetition is not independent evidence.'
        if duplicate_groups else 'No repeated fact statements after case, Unicode, and whitespace normalization.',
        duplicate_fields or ['facts'], 'Consolidate duplicate statements while preserving their source labels.' if duplicate_groups else None)

    warnings = sum(check['status'] == 'warning' for check in checks)
    return {
        'version': 1, 'mode': 'preflight', 'inputValid': True, 'canCreateOrder': True,
        'assessment': 'review-needed' if warnings else 'ready-for-owner-review',
        'requestSha256': request_hash(request), 'checks': checks, 'warningCount': warnings,
        'blockingCount': 0, 'questions': list(dict.fromkeys(check['question'] for check in checks if check['question'])),
        'counts': {'deliverables': len(request['deliverables']), 'constraints': len(request['constraints']),
                   'facts': len(request['facts']), 'uniqueStatements': len(groups),
                   'attributionGaps': len(source_gaps), 'duplicateGroups': len(duplicate_groups)},
        'briefGenerated': False, 'orderCreated': False, 'paymentInitiated': False,
        'disclosure': disclosure,
    }
