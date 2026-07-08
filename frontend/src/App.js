import React, { useState, useEffect, useCallback } from 'react';
import './App.css';

const API = 'http://localhost:8000';

// ---------------------------------------------------------------------------
// Utility helpers
// ---------------------------------------------------------------------------

function formatCardNumber(value) {
  return value.replace(/\D/g, '').slice(0, 16).replace(/(.{4})/g, '$1 ').trim();
}

function formatCurrency(amount, currency = 'USD') {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(amount);
}

function formatDate(iso) {
  return new Date(iso).toLocaleString();
}

function statusBadgeClass(s) {
  const map = {
    approved: 'badge badge-approved',
    declined: 'badge badge-declined',
    voided:   'badge badge-voided',
    refunded: 'badge badge-refunded',
    pending:  'badge badge-pending',
    failed:   'badge badge-failed',
  };
  return map[s] || 'badge';
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

async function apiPost(path, body) {
  const res = await fetch(`${API}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  return { ok: res.ok, status: res.status, data };
}

async function apiGet(path) {
  const res = await fetch(`${API}${path}`);
  const data = await res.json();
  return { ok: res.ok, data };
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function Alert({ type, message, onClose }) {
  if (!message) return null;
  return (
    <div className={`alert alert-${type}`} role="alert">
      <span>{message}</span>
      {onClose && <button className="alert-close" onClick={onClose}>×</button>}
    </div>
  );
}

function Spinner() {
  return <span className="spinner" aria-label="loading" />;
}

// ---------------------------------------------------------------------------
// Payment Form
// ---------------------------------------------------------------------------

const INITIAL_FORM = {
  cardholder_name: '',
  card_number: '',
  expiration_month: '',
  expiration_year: '',
  cvv: '',
  amount: '',
  currency: 'USD',
  description: '',
  merchant_reference: '',
};

function PaymentForm({ onSuccess }) {
  const [form, setForm] = useState(INITIAL_FORM);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((f) => ({
      ...f,
      [name]: name === 'card_number' ? formatCardNumber(value) : value,
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setResult(null);
    setLoading(true);
    try {
      const payload = {
        ...form,
        card_number: form.card_number.replace(/\s/g, ''),
        expiration_month: parseInt(form.expiration_month, 10),
        expiration_year: parseInt(form.expiration_year, 10),
      };
      const { ok, status, data } = await apiPost('/api/payments/charge/', payload);
      setResult({ ok, status, data });
      if (ok) {
        setForm(INITIAL_FORM);
        onSuccess && onSuccess();
      } else {
        const msg = data.detail || data.card || data.non_field_errors
          || JSON.stringify(data);
        setError(typeof msg === 'string' ? msg : JSON.stringify(msg));
      }
    } catch (err) {
      setError('Network error. Is the backend running?');
    } finally {
      setLoading(false);
    }
  };

  const currentYear = new Date().getFullYear();
  const years = Array.from({ length: 15 }, (_, i) => currentYear + i);
  const months = Array.from({ length: 12 }, (_, i) => i + 1);

  return (
    <section className="card-box">
      <h2 className="section-title">Process Payment</h2>

      {result && (
        <Alert
          type={result.ok ? 'success' : 'error'}
          message={
            result.ok
              ? `✓ Payment approved! Auth code: ${result.data.authorization_code}`
              : `✗ ${result.status === 402
                  ? `Payment declined: ${result.data.failure_reason}`
                  : 'Payment failed — check form errors below.'}`
          }
          onClose={() => setResult(null)}
        />
      )}
      {error && <Alert type="error" message={error} onClose={() => setError('')} />}

      <form onSubmit={handleSubmit} noValidate>
        <fieldset className="form-section">
          <legend>Card Details</legend>
          <div className="form-row">
            <div className="form-group full">
              <label htmlFor="cardholder_name">Cardholder Name</label>
              <input
                id="cardholder_name"
                name="cardholder_name"
                type="text"
                placeholder="Jane Doe"
                value={form.cardholder_name}
                onChange={handleChange}
                required
                autoComplete="cc-name"
              />
            </div>
          </div>
          <div className="form-row">
            <div className="form-group full">
              <label htmlFor="card_number">Card Number</label>
              <input
                id="card_number"
                name="card_number"
                type="text"
                placeholder="4111 1111 1111 1111"
                value={form.card_number}
                onChange={handleChange}
                required
                autoComplete="cc-number"
                inputMode="numeric"
              />
            </div>
          </div>
          <div className="form-row three-col">
            <div className="form-group">
              <label htmlFor="expiration_month">Exp Month</label>
              <select
                id="expiration_month"
                name="expiration_month"
                value={form.expiration_month}
                onChange={handleChange}
                required
              >
                <option value="">MM</option>
                {months.map((m) => (
                  <option key={m} value={m}>{String(m).padStart(2, '0')}</option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label htmlFor="expiration_year">Exp Year</label>
              <select
                id="expiration_year"
                name="expiration_year"
                value={form.expiration_year}
                onChange={handleChange}
                required
              >
                <option value="">YYYY</option>
                {years.map((y) => (
                  <option key={y} value={y}>{y}</option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label htmlFor="cvv">CVV</label>
              <input
                id="cvv"
                name="cvv"
                type="text"
                placeholder="123"
                value={form.cvv}
                onChange={handleChange}
                required
                maxLength={4}
                inputMode="numeric"
                autoComplete="cc-csc"
              />
            </div>
          </div>
        </fieldset>

        <fieldset className="form-section">
          <legend>Payment Details</legend>
          <div className="form-row two-col">
            <div className="form-group">
              <label htmlFor="amount">Amount</label>
              <input
                id="amount"
                name="amount"
                type="number"
                step="0.01"
                min="0.01"
                placeholder="99.99"
                value={form.amount}
                onChange={handleChange}
                required
                inputMode="decimal"
              />
            </div>
            <div className="form-group">
              <label htmlFor="currency">Currency</label>
              <select
                id="currency"
                name="currency"
                value={form.currency}
                onChange={handleChange}
              >
                {['USD', 'EUR', 'GBP', 'CAD', 'AUD', 'INR'].map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="form-row two-col">
            <div className="form-group">
              <label htmlFor="description">Description (optional)</label>
              <input
                id="description"
                name="description"
                type="text"
                placeholder="Order #1234"
                value={form.description}
                onChange={handleChange}
              />
            </div>
            <div className="form-group">
              <label htmlFor="merchant_reference">Merchant Ref (optional)</label>
              <input
                id="merchant_reference"
                name="merchant_reference"
                type="text"
                placeholder="ORD-1234"
                value={form.merchant_reference}
                onChange={handleChange}
              />
            </div>
          </div>
        </fieldset>

        <div className="test-cards">
          <strong>POC Test Cards</strong>
          <table>
            <thead>
              <tr><th>Card Number</th><th>Result</th></tr>
            </thead>
            <tbody>
              <tr><td><code>4111 1111 1111 1111</code></td><td>✓ Approved</td></tr>
              <tr><td><code>5500 0055 5555 5559</code></td><td>✓ Approved (MC)</td></tr>
              <tr><td><code>3782 8224 6310 005</code></td><td>✓ Approved (Amex)</td></tr>
              <tr><td><code>4111 1111 1111 0000</code></td><td>✗ Insufficient funds</td></tr>
              <tr><td><code>4111 1111 1111 9999</code></td><td>✗ Declined by issuer</td></tr>
              <tr><td>Any card, amount &gt; 9000</td><td>✗ Limit exceeded</td></tr>
            </tbody>
          </table>
        </div>

        <button type="submit" className="btn btn-primary btn-full" disabled={loading}>
          {loading ? <><Spinner /> Processing…</> : 'Charge Card'}
        </button>
      </form>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Refund / Void modal
// ---------------------------------------------------------------------------

function ActionModal({ txn, onClose, onDone }) {
  const [mode, setMode] = useState('refund'); // 'refund' | 'void'
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState('');
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setMsg(null);
    try {
      let res;
      if (mode === 'void') {
        res = await apiPost(`/api/payments/${txn.id}/void/`, {});
      } else {
        const body = {};
        if (amount) body.amount = amount;
        if (reason) body.reason = reason;
        res = await apiPost(`/api/payments/${txn.id}/refund/`, body);
      }
      if (res.ok) {
        setMsg({ type: 'success', text: `${mode === 'void' ? 'Void' : 'Refund'} successful!` });
        setTimeout(() => { onDone(); onClose(); }, 1200);
      } else {
        const err = res.data.error || res.data.detail || JSON.stringify(res.data);
        setMsg({ type: 'error', text: err });
      }
    } catch {
      setMsg({ type: 'error', text: 'Network error.' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>×</button>
        <h3>Transaction Action</h3>
        <p className="modal-txn-info">
          <strong>{txn.transaction_type.toUpperCase()}</strong>&nbsp;
          {formatCurrency(txn.amount, txn.currency)} &mdash;
          <span className={statusBadgeClass(txn.status)}>{txn.status}</span>
        </p>

        {msg && <Alert type={msg.type} message={msg.text} onClose={() => setMsg(null)} />}

        <div className="tab-bar">
          <button
            className={`tab ${mode === 'refund' ? 'active' : ''}`}
            onClick={() => setMode('refund')}
            disabled={txn.status !== 'approved'}
          >
            Refund
          </button>
          <button
            className={`tab ${mode === 'void' ? 'active' : ''}`}
            onClick={() => setMode('void')}
            disabled={!['approved', 'pending'].includes(txn.status)}
          >
            Void
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          {mode === 'refund' && (
            <>
              <div className="form-group">
                <label>Refund Amount (leave blank for full refund)</label>
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  max={txn.amount}
                  placeholder={txn.amount}
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                />
              </div>
              <div className="form-group">
                <label>Reason</label>
                <input
                  type="text"
                  placeholder="Customer return"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
              </div>
            </>
          )}
          {mode === 'void' && (
            <p className="void-warning">
              ⚠️ Voiding will cancel this transaction permanently.
            </p>
          )}
          <button type="submit" className="btn btn-primary btn-full" disabled={loading}>
            {loading ? <Spinner /> : `Confirm ${mode === 'void' ? 'Void' : 'Refund'}`}
          </button>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Transaction table
// ---------------------------------------------------------------------------

function TransactionTable({ transactions, onAction }) {
  if (!transactions.length) {
    return <p className="empty">No transactions yet.</p>;
  }
  return (
    <div className="table-wrapper">
      <table className="txn-table">
        <thead>
          <tr>
            <th>Type</th>
            <th>Card</th>
            <th>Amount</th>
            <th>Status</th>
            <th>Auth Code</th>
            <th>Created</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {transactions.map((t) => (
            <tr key={t.id}>
              <td><span className="txn-type">{t.transaction_type}</span></td>
              <td>
                {t.card ? (
                  <span className="card-info">
                    <span className="card-brand">{t.card.brand}</span>
                    &nbsp;****&nbsp;{t.card.last_four}
                  </span>
                ) : '—'}
              </td>
              <td className="amount">{formatCurrency(t.amount, t.currency)}</td>
              <td><span className={statusBadgeClass(t.status)}>{t.status}</span></td>
              <td><code>{t.authorization_code || '—'}</code></td>
              <td className="date">{formatDate(t.created_at)}</td>
              <td>
                {(t.status === 'approved' || t.status === 'pending') &&
                  t.transaction_type === 'charge' ? (
                  <button
                    className="btn btn-sm btn-secondary"
                    onClick={() => onAction(t)}
                  >
                    Actions
                  </button>
                ) : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Transactions panel
// ---------------------------------------------------------------------------

function TransactionsPanel() {
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('');
  const [selectedTxn, setSelectedTxn] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const path = filter ? `/api/transactions/?status=${filter}` : '/api/transactions/';
      const { ok, data } = await apiGet(path);
      if (ok) {
        setTransactions(data);
      } else {
        setError('Failed to load transactions.');
      }
    } catch {
      setError('Network error.');
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  return (
    <section className="card-box">
      <div className="section-header">
        <h2 className="section-title">Transaction History</h2>
        <div className="toolbar">
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">All statuses</option>
            {['approved', 'declined', 'voided', 'refunded', 'pending', 'failed'].map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <button className="btn btn-secondary" onClick={load} disabled={loading}>
            {loading ? <Spinner /> : '↺ Refresh'}
          </button>
        </div>
      </div>

      {error && <Alert type="error" message={error} onClose={() => setError('')} />}

      <TransactionTable
        transactions={transactions}
        onAction={(t) => setSelectedTxn(t)}
      />

      {selectedTxn && (
        <ActionModal
          txn={selectedTxn}
          onClose={() => setSelectedTxn(null)}
          onDone={load}
        />
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Stats bar
// ---------------------------------------------------------------------------

function StatsBar({ transactions }) {
  const approved = transactions.filter((t) => t.status === 'approved' && t.transaction_type === 'charge');
  const declined = transactions.filter((t) => t.status === 'declined');
  const total = approved.reduce((s, t) => s + parseFloat(t.amount), 0);

  return (
    <div className="stats-bar">
      <div className="stat">
        <span className="stat-value">{transactions.length}</span>
        <span className="stat-label">Total Txns</span>
      </div>
      <div className="stat">
        <span className="stat-value">{approved.length}</span>
        <span className="stat-label">Approved</span>
      </div>
      <div className="stat">
        <span className="stat-value">{declined.length}</span>
        <span className="stat-label">Declined</span>
      </div>
      <div className="stat">
        <span className="stat-value">{formatCurrency(total)}</span>
        <span className="stat-label">Volume</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Root App
// ---------------------------------------------------------------------------

function App() {
  const [transactions, setTransactions] = useState([]);
  const [refreshKey, setRefreshKey] = useState(0);

  const triggerRefresh = () => setRefreshKey((k) => k + 1);

  useEffect(() => {
    apiGet('/api/transactions/').then(({ ok, data }) => {
      if (ok) setTransactions(data);
    });
  }, [refreshKey]);

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="header-inner">
          <div className="logo">
            <span className="logo-icon">💳</span>
            <span className="logo-text">PayGate <span className="logo-poc">POC</span></span>
          </div>
          <span className="header-subtitle">Payment Gateway — Django + React + MySQL</span>
        </div>
      </header>

      <main className="main-content">
        <StatsBar transactions={transactions} />

        <div className="two-panel">
          <div className="panel-left">
            <PaymentForm onSuccess={triggerRefresh} />
          </div>
          <div className="panel-right">
            <TransactionsPanel key={refreshKey} />
          </div>
        </div>
      </main>

      <footer className="app-footer">
        POC — Not for production use &nbsp;|&nbsp; Django 3.2 · React 16 · MySQL
      </footer>
    </div>
  );
}

export default App;
