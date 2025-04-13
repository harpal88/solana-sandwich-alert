# Solana Sandwich Attack Detector


https://github.com/user-attachments/assets/9dce398c-2c62-4317-810f-d03d4142ee35


The **Solana Sandwich Attack Detector** is a web-based tool designed to analyze Solana token transactions and detect potential sandwich attacks. Sandwich attacks are a type of front-running where an attacker places orders both before and after a victim's transaction to profit from price movements.

## Features

- Analyze token transactions on the Solana blockchain.
- Detect potential sandwich attacks with detailed insights.
- Visualize transaction data with enhanced UI elements.
- Learn about sandwich attacks and their patterns.
- View recent analyses and explore transaction details on Solscan.

## Technologies Used

- **Frontend**: HTML, CSS (Bootstrap 5), JavaScript
- **Backend**: Python (Flask)
- **Blockchain**: Solana

## Getting Started

### Prerequisites

- Python 3.8 or higher.
- A Solana RPC endpoint for fetching transaction data.

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/solana-sandwich-alert.git
   cd solana-sandwich-alert
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up environment variables:
   - Configure your Solana RPC endpoint in the `.env` file.

### Running the Application

1. Start the backend server:
   ```bash
   python app.py
   ```

2. Open the application in your browser:
   ```
   http://localhost:5000
   ```



### Usage

1. Enter a Solana token address in the "Token Address" field.
2. Specify the number of transactions to analyze.
3. Click the "Analyze Token" button to start the analysis.
4. View the results, including potential sandwich attacks and transaction details.

### Project Structure

```
solana-sandwich-alert/
├── templates/
│   └── index.html       # Main HTML file
├── static/
│   ├── css/             # Custom styles (if any)
│   ├── js/              # Custom scripts (if any)
├── README.md            # Project documentation
├── app.py               # Backend server
├── config.json          # Configuration file
├── .env                 # Environment variables
└── run                  # Streamlit run script
```

## Contributing

Contributions are welcome! Please fork the repository and submit a pull request with your changes.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Solana](https://solana.com) for providing a robust blockchain platform.
- [Bootstrap](https://getbootstrap.com) for the responsive UI framework.
- [Solscan](https://solscan.io) for transaction exploration.
