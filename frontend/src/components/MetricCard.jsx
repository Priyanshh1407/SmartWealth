import React from 'react';

const MetricCard = ({ title, value, icon, colorClass, delayClass, isCircular, isWarning }) => {
  if (isCircular) {
    return (
      <div className={`glass-card rounded-xl p-md flex flex-col justify-between items-center relative overflow-hidden group animate-fade-slide-up ${delayClass}`}>
        <div className="absolute inset-0 bg-primary/10 opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
        <span className="font-label-caps text-outline w-full text-left relative z-10" title={title}>{title}</span>
        <div className="relative w-24 h-24 mt-xs flex items-center justify-center z-10">
          <svg className="w-full h-full transform -rotate-90" viewBox="0 0 100 100">
            <circle cx="50" cy="50" fill="none" r="40" stroke="rgba(255,255,255,0.1)" strokeWidth="8"></circle>
            <circle className="drop-shadow-[0_0_8px_rgba(76,215,246,0.8)]" cx="50" cy="50" fill="none" r="40" stroke="#4cd7f6" strokeDasharray="251.2" strokeDashoffset={251.2 * (1 - parseInt(value)/100)} strokeWidth="8"></circle>
          </svg>
          <span className="absolute font-title-md text-primary text-xl font-bold">{value}</span>
        </div>
      </div>
    );
  }

  return (
    <div className={`glass-card rounded-xl p-md flex flex-col justify-between group animate-fade-slide-up ${delayClass} ${isWarning ? 'border-l-2 border-l-tertiary' : ''}`}>
      <div className="flex justify-between items-start mb-sm">
        <span className={`font-label-caps pr-2 ${isWarning ? 'text-tertiary' : 'text-outline'}`} title={title}>{title}</span>
        <span className={`material-symbols-outlined text-[20px] shrink-0 ${colorClass}`}>{icon}</span>
      </div>
      <div className={`text-2xl md:text-3xl lg:text-4xl font-bold tracking-tight mt-auto break-all ${isWarning ? 'text-tertiary' : 'text-on-surface group-hover:text-primary transition-colors'}`}>
        {value}
      </div>
    </div>
  );
};

export default MetricCard;
