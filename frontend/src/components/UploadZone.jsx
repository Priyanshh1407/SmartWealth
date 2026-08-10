import React, { useCallback, useState, useRef } from 'react';

const UploadZone = ({ onFileUpload }) => {
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef(null);

  const handleDrag = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDragIn = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
      setIsDragging(true);
    }
  }, []);

  const handleDragOut = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFile(e.dataTransfer.files[0]);
    }
  }, []);

  const handleFile = (file) => {
    if (file && file.name.endsWith('.csv')) {
      const reader = new FileReader();
      reader.onload = (e) => {
        const text = e.target.result;
        onFileUpload(text);
      };
      reader.readAsText(file);
    } else {
      alert("Please upload a valid CSV file.");
    }
  };

  const handleFileInput = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFile(e.target.files[0]);
    }
  };

  const handleDownloadTemplate = () => {
    const templateContent = "transaction_id,date,merchant,amount,category,description\nTXN-001,2025-01-01,Office Depot,150.00,,Office supplies";
    const blob = new Blob([templateContent], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'smartwealth_template.csv';
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  };

  return (
    <div 
      className={`glass-card rounded-xl flex-1 flex flex-col min-h-0 overflow-hidden animate-fade-scale transition-all duration-300 ${
        isDragging ? 'border-primary bg-primary/5 shadow-[0_0_30px_rgba(76,215,246,0.3)]' : 'border-white/5'
      }`}
      onDragEnter={handleDragIn}
      onDragLeave={handleDragOut}
      onDragOver={handleDrag}
      onDrop={handleDrop}
    >
      <div className="flex justify-between items-center p-md border-b border-white/5 shrink-0">
        <h2 className="font-title-md text-on-surface">Upload Ledger</h2>
      </div>
      
      <div className="flex-1 flex flex-col items-center justify-center p-xl text-center">
        <div className={`w-24 h-24 rounded-full flex items-center justify-center mb-md transition-all duration-300 ${
          isDragging ? 'bg-primary/20 scale-110' : 'bg-black/40'
        }`}>
          <span className={`material-symbols-outlined text-[48px] ${
            isDragging ? 'text-primary' : 'text-on-surface-variant'
          }`}>
            cloud_upload
          </span>
        </div>
        
        <h3 className="font-headline-sm text-on-surface mb-xs">Drag & Drop your CSV</h3>
        <p className="font-body-md text-on-surface-variant max-w-[450px] mx-auto mb-lg text-center leading-relaxed">
          Upload your client's bank ledger to begin the AI Tax Audit. Ensure it matches the required template format.
        </p>
        
        <input 
          type="file" 
          accept=".csv" 
          className="hidden" 
          ref={fileInputRef}
          onChange={handleFileInput}
        />
        
        <div className="flex flex-col sm:flex-row items-center gap-sm">
          <button 
            onClick={() => fileInputRef.current.click()}
            className="px-lg py-sm bg-gradient-to-r from-primary to-primary/80 text-on-primary rounded-lg font-label-caps hover:scale-105 transition-all shadow-[0_0_15px_rgba(76,215,246,0.4)]"
          >
            Browse Files
          </button>
          
          <button 
            onClick={handleDownloadTemplate}
            className="px-lg py-sm bg-white/5 text-on-surface-variant rounded-lg font-label-caps hover:bg-white/10 hover:text-on-surface transition-all border border-white/10"
          >
            Download Template
          </button>
        </div>
      </div>
    </div>
  );
};

export default UploadZone;
