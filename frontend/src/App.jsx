import React, { useEffect } from 'react';
import Dashboard from './components/Dashboard';
import BackgroundShader from './components/BackgroundShader';
import useRunStore from './store/useRunStore';

function App() {
  const resumeIfNeeded = useRunStore(state => state.resumeIfNeeded);

  // On page load / reload, check if we were mid-run and resume polling
  useEffect(() => {
    resumeIfNeeded();
  }, [resumeIfNeeded]);
  return (
    <div className="bg-background text-on-surface font-body-lg min-h-screen overflow-hidden selection:bg-primary/30 flex items-center justify-center p-sm md:p-container-margin relative z-0">
      <BackgroundShader />
      {/* Dynamic Background Orbs */}
      <div className="fixed top-[-10%] left-[-10%] w-[50vw] h-[50vw] rounded-full bg-primary/10 blur-[150px] pointer-events-none z-[-1]"></div>
      <div className="fixed bottom-[-10%] right-[-10%] w-[60vw] h-[60vw] rounded-full bg-tertiary/10 blur-[150px] pointer-events-none z-[-1]"></div>
      <div className="fixed inset-0 z-[-2] bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-background/40 via-background/60 to-background/80"></div>
      
      <Dashboard />
    </div>
  );
}

export default App;
