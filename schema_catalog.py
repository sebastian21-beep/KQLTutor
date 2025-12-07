BASE_CATALOG = {
    "SecurityEvent": {
        "columns": [
            "TimeGenerated",
            "Computer",
            "Account",
            "EventID",
            "LogonResult",
            "HostName",
            "IpAddress",
        ],
        "sample_rows": [
            {
                "TimeGenerated": "2025-12-07T12:00:00Z",
                "Computer": "srv-01",
                "Account": "contoso\\alice",
                "EventID": 4625,
                "LogonResult": "Failed",
                "HostName": "srv-01",
                "IpAddress": "10.0.0.5",
            },
            {
                "TimeGenerated": "2025-12-07T12:30:00Z",
                "Computer": "srv-02",
                "Account": "contoso\\bob",
                "EventID": 4624,
                "LogonResult": "Success",
                "HostName": "srv-02",
                "IpAddress": "10.0.0.6",
            },
            {
                "TimeGenerated": "2025-12-07T13:10:00Z",
                "Computer": "srv-03",
                "Account": "contoso\\carol",
                "EventID": 4625,
                "LogonResult": "Failed",
                "HostName": "srv-03",
                "IpAddress": "10.0.0.7",
            },
        ],
    },
    "SigninLogs": {
        "columns": [
            "TimeGenerated",
            "UserPrincipalName",
            "IPAddress",
            "ResultType",
        ],
        "sample_rows": [
            {
                "TimeGenerated": "2025-12-07T12:05:00Z",
                "UserPrincipalName": "alice@contoso.com",
                "IPAddress": "20.1.2.3",
                "ResultType": "0",
            },
            {
                "TimeGenerated": "2025-12-07T12:40:00Z",
                "UserPrincipalName": "bob@contoso.com",
                "IPAddress": "20.1.2.9",
                "ResultType": "50074",
            },
            {
                "TimeGenerated": "2025-12-07T13:20:00Z",
                "UserPrincipalName": "carol@contoso.com",
                "IPAddress": "20.1.2.4",
                "ResultType": "0",
            },
        ],
    },
}

