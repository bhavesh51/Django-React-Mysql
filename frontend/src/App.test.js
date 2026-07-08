import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import App from './App';

// ---------------------------------------------------------------------------
// Mock fetch globally so tests don't need a real backend
// ---------------------------------------------------------------------------

const mockTransactions = [
  {
    id: 'aaaa-1111',
    transaction_type: 'charge',
    amount: '99.99',
    currency: 'USD',
    status: 'approved',
    authorization_code: 'ABC123DEF456',
    failure_reason: '',
    description: 'Test',
    merchant_reference: 'ORD-1',
    created_at: '2024-01-15T10:00:00Z',
    updated_at: '2024-01-15T10:00:00Z',
    card: {
      id: 'card-1111',
      cardholder_name: 'Jane Doe',
      last_four: '1111',
      brand: 'Visa',
      expiration_month: 12,
      expiration_year: 2030,
      created_at: '2024-01-15T09:59:00Z',
    },
  },
  {
    id: 'bbbb-2222',
    transaction_type: 'charge',
    amount: '50.00',
    currency: 'USD',
    status: 'declined',
    authorization_code: '',
    failure_reason: 'Insufficient funds',
    description: '',
    merchant_reference: '',
    created_at: '2024-01-15T11:00:00Z',
    updated_at: '2024-01-15T11:00:00Z',
    card: {
      id: 'card-2222',
      cardholder_name: 'Bob Smith',
      last_four: '0000',
      brand: 'Mastercard',
      expiration_month: 6,
      expiration_year: 2028,
      created_at: '2024-01-15T10:59:00Z',
    },
  },
];

const mockApprovedCharge = {
  id: 'cccc-3333',
  transaction_type: 'charge',
  amount: '75.00',
  currency: 'USD',
  status: 'approved',
  authorization_code: 'XYZ789ABC012',
  failure_reason: '',
  description: 'New charge',
  merchant_reference: 'ORD-2',
  created_at: '2024-01-15T12:00:00Z',
  updated_at: '2024-01-15T12:00:00Z',
  card: {
    id: 'card-3333',
    cardholder_name: 'Alice',
    last_four: '1111',
    brand: 'Visa',
    expiration_month: 12,
    expiration_year: 2030,
    created_at: '2024-01-15T11:59:00Z',
  },
};

const mockDeclinedCharge = {
  ...mockApprovedCharge,
  id: 'dddd-4444',
  status: 'declined',
  authorization_code: '',
  failure_reason: 'Insufficient funds',
};

function setupFetchMock(overrides = {}) {
  global.fetch = jest.fn().mockImplementation((url, opts) => {
    // Default: GET /api/transactions/ → return list
    if (!opts || opts.method !== 'POST') {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(overrides.transactions || mockTransactions),
      });
    }
    // POST /api/payments/charge/
    if (url.includes('/api/payments/charge/')) {
      const body = JSON.parse(opts.body);
      const isDeclined = overrides.forceDecline || body.card_number === '4111111111110000';
      return Promise.resolve({
        ok: !isDeclined,
        status: isDeclined ? 402 : 201,
        json: () => Promise.resolve(isDeclined ? mockDeclinedCharge : mockApprovedCharge),
      });
    }
    // POST /api/payments/:id/refund/
    if (url.includes('/refund/')) {
      return Promise.resolve({
        ok: true,
        status: 201,
        json: () => Promise.resolve({ ...mockApprovedCharge, transaction_type: 'refund', id: 'refund-1' }),
      });
    }
    // POST /api/payments/:id/void/
    if (url.includes('/void/')) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ ...mockApprovedCharge, status: 'voided' }),
      });
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
  });
}

afterEach(() => {
  if (global.fetch && global.fetch.mockRestore) {
    global.fetch.mockRestore();
  }
  jest.clearAllMocks();
});

// ---------------------------------------------------------------------------
// App rendering
// ---------------------------------------------------------------------------

describe('App — initial render', () => {
  test('renders the PayGate header', async () => {
    setupFetchMock();
    render(<App />);
    expect(screen.getByText(/PayGate/i)).toBeInTheDocument();
  });

  test('renders the Process Payment section', async () => {
    setupFetchMock();
    render(<App />);
    expect(screen.getByText(/Process Payment/i)).toBeInTheDocument();
  });

  test('renders the Transaction History section', async () => {
    setupFetchMock();
    render(<App />);
    expect(screen.getByText(/Transaction History/i)).toBeInTheDocument();
  });

  test('renders stats bar', async () => {
    setupFetchMock();
    render(<App />);
    expect(screen.getByText(/Total Txns/i)).toBeInTheDocument();
    expect(screen.getByText(/Approved/i)).toBeInTheDocument();
    expect(screen.getByText(/Declined/i)).toBeInTheDocument();
    expect(screen.getByText(/Volume/i)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// PaymentForm
// ---------------------------------------------------------------------------

describe('PaymentForm — card number formatting', () => {
  test('formats card number with spaces', async () => {
    setupFetchMock();
    render(<App />);
    const input = screen.getByLabelText(/Card Number/i);
    fireEvent.change(input, { target: { value: '4111111111111111', name: 'card_number' } });
    expect(input.value).toBe('4111 1111 1111 1111');
  });

  test('limits card number to 16 digits', async () => {
    setupFetchMock();
    render(<App />);
    const input = screen.getByLabelText(/Card Number/i);
    fireEvent.change(input, { target: { value: '41111111111111119999', name: 'card_number' } });
    // After formatting 16 digits = "4111 1111 1111 1111" (19 chars with spaces)
    expect(input.value.replace(/\s/g, '').length).toBeLessThanOrEqual(16);
  });
});

describe('PaymentForm — test card reference table', () => {
  test('renders POC test card table', async () => {
    setupFetchMock();
    render(<App />);
    expect(screen.getByText(/POC Test Cards/i)).toBeInTheDocument();
    expect(screen.getByText(/4111 1111 1111 1111/i)).toBeInTheDocument();
  });
});

describe('PaymentForm — submit approved charge', () => {
  test('shows success alert on approved charge', async () => {
    setupFetchMock();
    render(<App />);

    fireEvent.change(screen.getByLabelText(/Cardholder Name/i), {
      target: { value: 'Jane Doe', name: 'cardholder_name' },
    });
    fireEvent.change(screen.getByLabelText(/Card Number/i), {
      target: { value: '4111111111111111', name: 'card_number' },
    });
    fireEvent.change(screen.getByLabelText(/Exp Month/i), {
      target: { value: '12', name: 'expiration_month' },
    });
    fireEvent.change(screen.getByLabelText(/Exp Year/i), {
      target: { value: '2030', name: 'expiration_year' },
    });
    fireEvent.change(screen.getByLabelText(/CVV/i), {
      target: { value: '123', name: 'cvv' },
    });
    fireEvent.change(screen.getByLabelText(/Amount/i), {
      target: { value: '99.99', name: 'amount' },
    });

    fireEvent.click(screen.getByRole('button', { name: /Charge Card/i }));

    await waitFor(() => {
      expect(screen.getByText(/Payment approved/i)).toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// Transaction history
// ---------------------------------------------------------------------------

describe('TransactionTable', () => {
  test('renders transaction rows after load', async () => {
    setupFetchMock();
    render(<App />);

    await waitFor(() => {
      // Jane Doe's card should appear
      expect(screen.getAllByText(/Visa/i).length).toBeGreaterThanOrEqual(1);
    });
  });

  test('renders status badges', async () => {
    setupFetchMock();
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('approved')).toBeInTheDocument();
      expect(screen.getByText('declined')).toBeInTheDocument();
    });
  });

  test('renders action button for approved charges', async () => {
    setupFetchMock();
    render(<App />);

    await waitFor(() => {
      const actionBtns = screen.getAllByRole('button', { name: /Actions/i });
      expect(actionBtns.length).toBeGreaterThanOrEqual(1);
    });
  });
});

// ---------------------------------------------------------------------------
// ActionModal — refund / void
// ---------------------------------------------------------------------------

describe('ActionModal', () => {
  async function openModal() {
    setupFetchMock();
    render(<App />);
    await waitFor(() => screen.getAllByRole('button', { name: /Actions/i }));
    fireEvent.click(screen.getAllByRole('button', { name: /Actions/i })[0]);
  }

  test('opens modal when Actions clicked', async () => {
    await openModal();
    expect(screen.getByText(/Transaction Action/i)).toBeInTheDocument();
  });

  test('shows Refund and Void tabs', async () => {
    await openModal();
    expect(screen.getByRole('button', { name: /Refund/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Void/i })).toBeInTheDocument();
  });

  test('closes modal on overlay click', async () => {
    await openModal();
    fireEvent.click(document.querySelector('.modal-overlay'));
    await waitFor(() => {
      expect(screen.queryByText(/Transaction Action/i)).not.toBeInTheDocument();
    });
  });

  test('shows success message after refund', async () => {
    await openModal();
    fireEvent.click(screen.getByRole('button', { name: /Confirm Refund/i }));
    await waitFor(() => {
      expect(screen.getByText(/Refund successful/i)).toBeInTheDocument();
    });
  });

  test('switches to void tab', async () => {
    await openModal();
    fireEvent.click(screen.getByRole('button', { name: /^Void$/i }));
    expect(screen.getByText(/Voiding will cancel/i)).toBeInTheDocument();
  });
});
