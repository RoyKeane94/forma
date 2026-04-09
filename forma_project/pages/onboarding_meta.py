"""Copy and structure for each onboarding step (tabs, headers, sidebar)."""

ONBOARDING_STEPS = [
    {
        'tab': 'About you',
        'title': 'About you',
        'step_label': 'Step 1 of 6',
        'description': (
            "The basics — your name, where you're based, and a short description "
            'of who you are and how you train.'
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
        'step_label': 'Step 2 of 6',
        'description': (
            'Your certifications and credentials. These appear verbatim on your profile — be specific.'
        ),
        'sidebar_label': 'What to include',
        'sidebar_tip': (
            'List the qualification name exactly as it appears on your certificate, '
            'then add the issuing body or year in the detail field.'
        ),
        'sidebar_example_label': 'Example',
        'sidebar_example': (
            'Name: "Pre & Postnatal Certificate"\nDetail: "Guild of Pregnancy & Postnatal Exercise"'
        ),
    },
    {
        'tab': 'Specialisms',
        'title': 'What you do best',
        'step_label': 'Step 3 of 6',
        'description': (
            'Up to four areas. Keep them short — these are labels, not descriptions.'
        ),
        'sidebar_label': 'Keep it short',
        'sidebar_tip': (
            "These are labels, not descriptions. Clients scan them quickly to work out if you're "
            'relevant. Two or three words each is ideal.'
        ),
        'sidebar_example_label': 'Good examples',
        'sidebar_example': (
            'Strength Training\nBody Composition\nPre & Postnatal\nInjury Rehab'
        ),
    },
    {
        'tab': 'Logistics',
        'title': 'Logistics',
        'step_label': 'Step 4 of 6',
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
        'step_label': 'Step 5 of 6',
        'description': (
            "Be upfront. Clients who see your rates before enquiring are warmer leads — they've "
            'already decided the price works for them.'
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
        'tab': 'Photos & Instagram',
        'title': 'Photos & Instagram',
        'step_label': 'Step 6 of 6',
        'description': (
            'Upload six photos that represent your training style. These are what a potential '
            'client sees before they read anything else.'
        ),
        'sidebar_label': 'Photo tips',
        'sidebar_tip': (
            'Mix action shots (training a client, demonstrating an exercise) with at least one clear '
            'photo of your face. Avoid dark gyms if possible — natural light reads better.'
        ),
        'sidebar_example_label': 'Good mix',
        'sidebar_example': (
            '1 portrait · 2 training clients · 2 outdoor or gym action · 1 with equipment'
        ),
    },
]

TAB_LABELS = [s['tab'] for s in ONBOARDING_STEPS]
