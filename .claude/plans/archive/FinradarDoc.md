## Webhook API
v1.0.0
Webhook Notifications
Receive real-time updates for trading setups and triggers.
Method
POST
Content-Type
application/json
Timeout
5 seconds
The system sends webhook notifications for two types of events:
New Setup Detected: When a new trading setup is identified (via Realtime or Polling).
Setup Triggered: When a setup's price conditions are met (Entry Trigger).
Payload Structure

All webhooks share a consistent JSON structure.

## JSON Schema
{
> "event_type": "string",       // "new_setup" or "trigger"
> "setup_id": "string",         // Unique identifier for the setup
> "symbol": "string",           // Trading pair (e.g., "BTCUSD", "EURUSD")
> "direction": "string",        // "buy" or "sell"
> "entry_zone": [float, float], // Array containing [min_entry, max_entry]
> "stop_loss": float,           // Stop Loss price
> "tp1": float,                 // Take Profit 1 price
> "tp2": float,                 // Take Profit 2 price
> "current_price": float,       // Live price at the time of the event
> "timestamp": "iso-string"     // UTC timestamp (ISO 8601)
}
Field Descriptions

# Field Type Description
event_type	string	The type of event. Values: new_setup or trigger.
setup_id	string	The unique ID of the trading setup from the database.
symbol	string	The asset symbol (e.g., **XAUUSD**, **BTCUSD**).
direction	string	The trade direction: buy (Long) or sell (Short).
entry_zone	[float]	A list of two floats representing the entry price range.
stop_loss	float	The invalidation price level.
tp1	float	First take profit target.
tp2	float	Second take profit target.
current_price	float	The market price when the notification was generated. For trigger events, this is the trigger price.
timestamp	string	Exact time of the event in UTC ISO 8601 format.
Examples

## New Setup
Sent when the AI/Algorithm detects a potential trade setup.
Payload
Copy
{
> "event_type": "new_setup",
> "setup_id": "550e8400-e29b-41d4-a716-446655440000",
> "symbol": "BTCUSD",
> "direction": "buy",
> "entry_zone": [95000.0, 95500.0],
> "stop_loss": 94000.0,
> "tp1": 97000.0,
> "tp2": 100000.0,
> "current_price": 95120.50,
> "timestamp": "2024-12-26T12:00:00.000000+00:00"
}
Trigger Notification
Sent when price entering entry zone and the setup is "triggered".
Payload
Copy
{
> "event_type": "trigger",
> "setup_id": "550e8400-e29b-41d4-a716-446655440000",
> "symbol": "BTCUSD",
> "direction": "buy",
> "entry_zone": [95000.0, 95500.0],
> "stop_loss": 94000.0,
> "tp1": 97000.0,
> "tp2": 100000.0,
> "current_price": 95050.00,
> "timestamp": "2024-12-26T12:15:30.123456+00:00"
}
© 2024 Market Signal API. All rights reserved.