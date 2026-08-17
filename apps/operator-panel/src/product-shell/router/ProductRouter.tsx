import { HashRouter, Route, Routes } from 'react-router-dom';

import { AppShell } from '../shell/AppShell';
import { CollectionPage } from '../pages/CollectionPage';
import { AgentsPage, ApprovalsPage, LibraryPage } from '../pages/GovernedCollections';
import { NewWorkPage } from '../pages/NewWorkPage';
import { TaskPage } from '../pages/TaskPage';
import { SettingsShell } from '../settings/SettingsShell';
import { LegacyOperatorApp } from '../legacy/LegacyOperatorApp';

function ProductShellRoutes() {
  return <AppShell><Routes><Route path="/" element={<NewWorkPage />} /><Route path="/task/:taskId" element={<TaskPage />} /><Route path="/task/:taskId/workspace" element={<TaskPage />} /><Route path="/library" element={<LibraryPage />} /><Route path="/approvals" element={<ApprovalsPage />} /><Route path="/agents" element={<AgentsPage />} /><Route path="/automations" element={<CollectionPage title="Automations" body="Automation capabilities are not registered for this desktop runtime." />} /><Route path="/settings" element={<SettingsShell />} /><Route path="/settings/:section" element={<SettingsShell />} /><Route path="*" element={<NewWorkPage />} /></Routes></AppShell>;
}

/** The former panel stays directly reachable for advanced/system workflows. */
export function ProductRouter() { return <HashRouter><Routes><Route path="/system/*" element={<LegacyOperatorApp />} /><Route path="*" element={<ProductShellRoutes />} /></Routes></HashRouter>; }
