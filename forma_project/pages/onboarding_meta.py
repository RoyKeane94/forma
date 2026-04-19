"""Copy and structure for each onboarding step (tabs, headers, sidebar)."""

ONBOARDING_STEPS = [
    {
        'tab': 'About you',
        'title': 'About you',
        'step_label': 'Step 1 of 7',
        'description': (
            "The basics — your name, where you're based, a short description "
            'of who you are and how you train, optional client contact details, and your photo.'
        ),
        'sidebar_label': 'Writing your bio',
        'sidebar_tip': (
            'Write in the first person. Be specific about who you work with and how — '
            'not just what qualifications you have.'
        ),
        'sidebar_example_label': 'Good example',
        'sidebar_example': (
            '"I work primarily with adults in their 30s and 40s who\'ve been in and out '
            'of gyms without seeing results. Strength is always the foundation..."'
        ),
    },
    {
        'tab': 'Qualifications',
        'title': 'Qualifications',
        'step_label': 'Step 2 of 7',
        'description': (
            'Your certifications and credentials. These appear verbatim on your profile — be specific.'
        ),
        'sidebar_label': 'What to include',
        'sidebar_tip': (
            'List the qualification name exactly as it appears on your certificate, '
            'then use the next field to explain in plain language what it qualifies you to do for clients.'
        ),
        'sidebar_example_label': 'Example',
        'sidebar_example': (
            'Name: "Pre & Postnatal Certificate"\n'
            'Client-facing line: "Safe exercise planning before and after birth — including pelvic floor and core rebuild."'
        ),
    },
    {
        'tab': 'Specialisms',
        'title': 'What you do best',
        'step_label': 'Step 3 of 7',
        'description': (
            'Up to four areas: a short title plus an optional one-line description so clients know what you mean.'
        ),
        'sidebar_label': 'Titles and blurbs',
        'sidebar_tip': (
            'Keep each title to a few words (it scans fast on your page). Use the description line to spell out '
            'who it is for or what you cover — one sentence is enough.'
        ),
        'sidebar_example_label': 'Good examples',
        'sidebar_example': (
            'Strength Training\nBody Composition\nPre & Postnatal\nInjury Rehab'
        ),
    },
    {
        'tab': 'Logistics',
        'title': 'Logistics',
        'step_label': 'Step 4 of 7',
        'description': (
            "Where you train and which areas you cover. Clients use this to work out whether you're "
            'the right fit geographically.'
        ),
        'sidebar_label': 'Primary area',
        'sidebar_tip': (
            'This is used for local SEO — "personal trainer Clapham" searches. '
            'Make it the area where you do most sessions.'
        ),
        'sidebar_example_label': None,
        'sidebar_example': None,
    },
    {
        'tab': 'Pricing',
        'title': 'Pricing',
        'step_label': 'Step 5 of 7',
        'description': (
            'Be upfront. Clients who see your rates before enquiring are warmer leads. '
            "They've already decided the price works for them."
        ),
        'sidebar_label': 'On showing prices',
        'sidebar_tip': (
            'Clients who see rates before enquiring are warmer leads. Hiding prices doesn\'t stop '
            'people caring about cost — it just means they find out later.'
        ),
        'sidebar_example_label': None,
        'sidebar_example': None,
    },
    {
        'tab': 'Photos, video & Instagram',
        'title': 'Photos, video & Instagram',
        'step_label': 'Step 6 of 7',
        'description': (
            'Optional intro video, six gallery photos, and your Instagram handle. '
            'If you turn the video block on but have not uploaded a clip yet, your public page shows a tasteful placeholder.'
        ),
        'sidebar_label': 'Intro video',
        'sidebar_tip': (
            'Keep an intro under about a minute — enough for someone to sense your personality and coaching style. '
            'If you enable “show on profile” with no file yet, clients still see the block with a “coming soon” style placeholder.'
        ),
        'sidebar_example_label': 'Photo mix',
        'sidebar_example': (
            '1 portrait · 2 training clients · 2 outdoor or gym action · 1 with equipment'
        ),
    },
    {
        'tab': 'Reviews',
        'title': 'Client reviews',
        'step_label': 'Step 7 of 7',
        'description': (
            'You can add up to three short testimonials when you create your profile. '
            'They appear on your public page once both a name and a quote are filled in for each slot.'
        ),
        'sidebar_label': 'Social proof',
        'sidebar_tip': (
            'First name plus initial (e.g. “Jamie T.”) is enough if clients prefer not to be fully named. '
            'Short, specific quotes beat generic praise every time.'
        ),
        'sidebar_example_label': 'Example',
        'sidebar_example': (
            '"Maya rebuilt my confidence in the gym after a shoulder injury — sessions are structured but never rigid."'
        ),
    },
]

TAB_LABELS = [s['tab'] for s in ONBOARDING_STEPS]
