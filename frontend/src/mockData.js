export const mockMetrics = {
    totalScanned: 260,
    totalDeductible: 1250450.50,
    accuracy: 80,
    actionRequired: 3
  };
  
  export const mockTransactions = [
    {
      id: "TXN-1095",
      date: "2025-01-15",
      merchant: "Unknown",
      description: "MISC CHRG",
      amount: 17133.89,
      category: "Unknown",
      confidence: 0.4,
      status: "unresolved"
    },
    {
      id: "TXN-1187",
      date: "2025-01-16",
      merchant: "Flipkart",
      description: "NEFT-123-FLIPKART-STATIONERY",
      amount: 33259.70,
      category: "Office Supplies",
      confidence: 0.9,
      status: "deductible"
    },
    {
      id: "TXN-1038",
      date: "2025-01-17",
      merchant: "Apple India",
      description: "POS 4892 APPLE BKC MUMBAI",
      amount: 163572.42,
      category: "Hardware & Equipment",
      confidence: 1.0,
      status: "deductible"
    },
    {
      id: "TXN-1292",
      date: "2025-01-18",
      merchant: "PVR INOX",
      description: "UPI/987654/PVR/DELHI",
      amount: 4500.00,
      category: "Entertainment",
      confidence: 0.9,
      status: "not_deductible"
    },
    {
      id: "TXN-1192",
      date: "2025-01-19",
      merchant: "GitHub",
      description: "BIL/ONLPAY/GITHUB INC",
      amount: 13463.88,
      category: "Software Subscriptions",
      confidence: 0.95,
      status: "deductible"
    }
  ];
