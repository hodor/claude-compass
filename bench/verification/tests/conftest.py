def pytest_configure(config):
    config.addinivalue_line("markers", "slow: tests that build the seeded project and run its checks")
