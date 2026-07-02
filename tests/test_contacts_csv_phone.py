"""_parse_contacts_csv should carry Phone / LinkedIn columns (ZoomInfo pulls)
through to the contact dict so the same-day call cards show click-to-call numbers.
"""
import flowdrip_app as fa


def test_phone_and_linkedin_columns_parsed():
    csv_text = ("First Name,Last Name,Email,Company,Title,Phone,LinkedIn\n"
                "Jordan,Centofanti,jordan@x.com,3D Systems,Supervisor,"
                "(720) 643-1176,https://linkedin.com/in/jc\n")
    c = fa._parse_contacts_csv(csv_text)[0]
    assert c["email"] == "jordan@x.com"
    assert c["first_name"] == "Jordan"
    assert c["last_name"] == "Centofanti"
    assert c["phone_office"] == "(720) 643-1176"
    assert c["linkedin"] == "https://linkedin.com/in/jc"


def test_mobile_column_maps_to_phone_mobile():
    c = fa._parse_contacts_csv("Email,MobilePhone\nx@y.com,555-1212\n")[0]
    assert c["phone_mobile"] == "555-1212"
    assert "phone_office" not in c


def test_no_phone_columns_still_parses():
    c = fa._parse_contacts_csv("email,first_name\na@b.com,Al\n")[0]
    assert c["email"] == "a@b.com"
    assert "phone_office" not in c and "phone_mobile" not in c
