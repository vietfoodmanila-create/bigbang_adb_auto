from cloud import Cloud, make_device_uid
c = Cloud()
print(c.ping())

token = c.login("you@example.com", "Pass@12345")
print("TOKEN =", token[:20], "...")

print(c.license_activate("A1B2C3D4E5F60718293A4B5C6D7E8F90", make_device_uid(), "MyPC"))
print(c.license_status())
