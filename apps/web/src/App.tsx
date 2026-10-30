import { lazy, Suspense } from 'react';
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
  useParams,
} from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { SiteLayout } from './components/SiteLayout';
import { HomePage } from './pages/HomePage';
import { FeaturesPage } from './pages/FeaturesPage';
import { PricingPage } from './pages/PricingPage';
import { NemotronPage } from './pages/NemotronPage';
import { NotFoundPage } from './pages/NotFoundPage';

// Account forms (and Zod validation) and the workspace load only when visited.
const AuthPage = lazy(() =>
  import('./pages/AuthPage').then((m) => ({ default: m.AuthPage })),
);
const WorkspaceRoot = lazy(() =>
  import('./workspace/Shell').then((m) => ({ default: m.WorkspaceRoot })),
);
const page = <K extends string>(
  load: () => Promise<Record<K, React.ComponentType>>,
  name: K,
) => lazy(() => load().then((m) => ({ default: m[name] })));

const Overview = page(() => import('./workspace/pages/Overview'), 'Overview');
const Datasets = page(() => import('./workspace/pages/Data'), 'Datasets');
const Profile = page(() => import('./workspace/pages/Data'), 'Profile');
const ChurnDefinitions = page(
  () => import('./workspace/pages/Churn'),
  'ChurnDefinitions',
);
const DefineChurn = page(
  () => import('./workspace/pages/Churn'),
  'DefineChurn',
);
const Models = page(() => import('./workspace/pages/Models'), 'Models');
const TrainModel = page(() => import('./workspace/pages/Models'), 'TrainModel');
const ModelDetail = page(
  () => import('./workspace/pages/Models'),
  'ModelDetail',
);
const ScoreBatches = page(
  () => import('./workspace/pages/Scores'),
  'ScoreBatches',
);
const NewScore = page(() => import('./workspace/pages/Scores'), 'NewScore');
const ScoreBatch = page(() => import('./workspace/pages/Scores'), 'ScoreBatch');
const Plays = page(() => import('./workspace/pages/Plays'), 'Plays');
const Investigate = page(
  () => import('./workspace/pages/Investigate'),
  'Investigate',
);
const Analyses = page(() => import('./workspace/pages/Analyses'), 'Analyses');
const AnalysisDetail = page(
  () => import('./workspace/pages/Analyses'),
  'AnalysisDetail',
);
const Copilot = page(() => import('./workspace/pages/Copilot'), 'Copilot');
const Inbox = page(() => import('./workspace/pages/Inbox'), 'Inbox');
const Jobs = page(() => import('./workspace/pages/Manage'), 'Jobs');
const Sources = page(() => import('./workspace/pages/Sources'), 'Sources');
const ConnectorGuide = page(
  () => import('./workspace/pages/ConnectorGuide'),
  'ConnectorGuide',
);
const Playbooks = page(
  () => import('./workspace/pages/Playbooks'),
  'Playbooks',
);
const PlaybookDetail = page(
  () => import('./workspace/pages/Playbooks'),
  'PlaybookDetail',
);
const TeamPage = page(() => import('./workspace/pages/Team'), 'TeamPage');
const Monitoring = page(
  () => import('./workspace/pages/Monitoring'),
  'Monitoring',
);
const MonitorReportDetail = page(
  () => import('./workspace/pages/Monitoring'),
  'MonitorReportDetail',
);
const SourceDetail = page(
  () => import('./workspace/pages/Sources'),
  'SourceDetail',
);
const Settings = page(() => import('./workspace/pages/Manage'), 'Settings');

/** Redirect an earlier workspace path, keeping its :id and query string. */
function Legacy({ to }: { to: string }) {
  const { id } = useParams();
  const { search } = useLocation();
  return <Navigate replace to={to.replace(':id', id ?? '') + search} />;
}

const LEGACY: [string, string][] = [
  ['datasets', '/app/data'],
  ['datasets/:id', '/app/data/:id'],
  ['datasets/:id/setup', '/app/data/:id/churn'],
  ['setup', '/app/data'],
  ['setup/data', '/app/data'],
  ['setup/data/:id', '/app/data/:id'],
  ['setup/data/:id/define', '/app/data/:id/churn'],
  ['setup/train', '/app/models/new'],
  ['setup/connections', '/app/sources'],
  ['connections', '/app/sources'],
  ['experiments', '/app/models'],
  ['experiments/new', '/app/models/new'],
  ['experiments/:id', '/app/models/:id'],
  ['model', '/app/models'],
  ['model/jobs', '/app/jobs'],
  ['model/:id', '/app/models/:id'],
  ['customers', '/app/scores'],
  ['customers/new', '/app/scores/new'],
  ['customers/:id', '/app/scores/:id'],
  ['accounts', '/app/scores'],
  ['accounts/new', '/app/scores/new'],
  ['accounts/:id', '/app/scores/:id'],
  ['analyses/:id', '/app/analyses/:id'],
  ['insights', '/app/investigate'],
  ['insights/saved', '/app/analyses'],
  ['insights/saved/:id', '/app/analyses/:id'],
  ['retention', '/app/plays'],
  ['copilot', '/app/ask'],
];

const fallback = (
  <div className="grid min-h-screen place-items-center bg-slate-50">
    <Loader2 className="size-6 animate-spin text-brand-600" />
  </div>
);

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<SiteLayout />}>
          <Route index element={<HomePage />} />
          <Route path="product" element={<FeaturesPage />} />
          <Route path="features" element={<Navigate to="/product" replace />} />
          <Route path="nemotron" element={<NemotronPage />} />
          <Route path="pricing" element={<PricingPage />} />
          <Route
            path="login"
            element={
              <Suspense fallback={fallback}>
                <AuthPage mode="login" />
              </Suspense>
            }
          />
          <Route
            path="signup"
            element={
              <Suspense fallback={fallback}>
                <AuthPage mode="signup" />
              </Suspense>
            }
          />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
        <Route
          path="app"
          element={
            <Suspense fallback={fallback}>
              <WorkspaceRoot />
            </Suspense>
          }
        >
          <Route index element={<Overview />} />
          <Route path="data" element={<Datasets />} />
          <Route path="data/:id" element={<Profile />} />
          <Route path="data/:id/churn" element={<DefineChurn />} />
          <Route path="churn" element={<ChurnDefinitions />} />
          <Route path="models" element={<Models />} />
          <Route path="models/new" element={<TrainModel />} />
          <Route path="models/:id" element={<ModelDetail />} />
          <Route path="scores" element={<ScoreBatches />} />
          <Route path="scores/new" element={<NewScore />} />
          <Route path="scores/:id" element={<ScoreBatch />} />
          <Route path="plays" element={<Plays />} />
          <Route path="investigate" element={<Investigate />} />
          <Route path="analyses" element={<Analyses />} />
          <Route path="analyses/:id" element={<AnalysisDetail />} />
          <Route path="ask" element={<Copilot />} />
          <Route path="inbox" element={<Inbox />} />
          <Route path="jobs" element={<Jobs />} />
          <Route path="sources" element={<Sources />} />
          <Route path="sources/:id" element={<SourceDetail />} />
          <Route path="guides/connectors" element={<ConnectorGuide />} />
          <Route path="playbooks" element={<Playbooks />} />
          <Route path="monitoring" element={<Monitoring />} />
          <Route path="team" element={<TeamPage />} />
          <Route path="monitoring/:id" element={<MonitorReportDetail />} />
          <Route path="playbooks/:id" element={<PlaybookDetail />} />
          <Route path="settings" element={<Settings />} />
          {LEGACY.map(([from, to]) => (
            <Route key={from} path={from} element={<Legacy to={to} />} />
          ))}
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
