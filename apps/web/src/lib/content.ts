/** Marketing copy is separate from UI. Roadmap items must not look like shipped integrations. */
export const capabilities = [
  {
    id: 'readiness',
    number: '01',
    title: 'Start with a clearer picture.',
    category: 'Data readiness',
    status: 'available',
    description:
      'Bring a CSV or Excel sheet. Check missing values, labels, identifiers, and potential leakage before training.',
    details: [
      'CSV & Excel import',
      'Data quality and target checks',
      'Explicit feature and outcome confirmation',
    ],
  },
  {
    id: 'models',
    number: '02',
    title: 'Let your evidence pick the model.',
    category: 'Model comparison',
    status: 'available',
    description:
      'Compare Logistic Regression, Random Forest, and XGBoost against a simple baseline. Keep the final test separate.',
    details: [
      'Reproducible model comparison',
      'Validation metrics and calibration',
      'Saved experiments and evidence',
    ],
  },
  {
    id: 'shortlist',
    number: '03',
    title: 'Make the next conversation count.',
    category: 'Customer priorities',
    status: 'available',
    description:
      'Score a separate customer sheet, explore risk and value, and export a shortlist that fits your contact budget.',
    details: [
      'Current-customer scoring',
      'Contact budget and ranked export',
      'Segments and model sensitivity',
    ],
  },
  {
    id: 'agent',
    number: '04',
    title: 'Ask the question behind the number.',
    category: 'Evidence copilot',
    status: 'available',
    description:
      'The NVIDIA Nemotron assistant, served by Nebius, uses tools to inspect recorded data and model results. Follow the evidence behind an answer.',
    details: [
      'Tool-backed dataset and run context',
      'Evidence-linked explanations',
      'Bounded, explicitly authorized training',
    ],
  },
  {
    id: 'connect',
    number: '05',
    title: 'One customer. The whole story.',
    category: 'Connected SaaS signals',
    status: 'planned',
    description:
      'Bring billing, product activity, and support history into an account timeline. See the moments a single spreadsheet can miss.',
    details: [
      'Billing and CRM connectors',
      'Usage and support timelines',
      'Time-aware evaluation',
    ],
  },
  {
    id: 'actions',
    number: '06',
    title: 'From insight to a thoughtful next move.',
    category: 'Retention workspace',
    status: 'planned',
    description:
      'Draft playbook-informed next steps, review them with your team, and track what happened after the conversation.',
    details: [
      'Playbook-grounded action drafts',
      'Human-reviewed CRM tasks',
      'Outcome tracking and experiments',
    ],
  },
] as const;

export const questions = [
  [
    'Who is this for?',
    'Subscription and SaaS teams that have customer history but need a clearer way to prioritize retention conversations. The first release works with labeled customer tables.',
  ],
  [
    'Do I need to know machine learning?',
    'You will need to confirm your churn definition and which data exists before that outcome. The product is designed to explain model comparisons and evidence in plain language, without hiding the assumptions.',
  ],
  [
    'Is this just AutoML?',
    'Model comparison is one part of the workflow. Customer Intelligence connects data readiness, reproducible evaluation, a ranked contact shortlist, and a tool-backed assistant. Connected CRM actions are part of the roadmap.',
  ],
  [
    'Does a high risk score tell me how to save a customer?',
    'It helps prioritize an investigation. It does not prove why a customer will leave or which offer will work. The roadmap includes reviewed actions and outcome experiments to learn what actually helps.',
  ],
  [
    'Can I connect my CRM today?',
    'Not yet. CSV and Excel import are available in the backend. Billing, product, and CRM connectors are planned. This website is a product preview; account access and the upload and retention screens are still being built.',
  ],
] as const;
