# Disposable / temporary email domain blocklist.
#
# Purpose: block signup with throwaway inboxes (10minutemail, guerrillamail,
# mailinator, tempmail, etc.) that let one person register an unlimited
# number of accounts to abuse free-tier quotas/trials/referral rewards.
#
# This is a curated static list of the most widely-used disposable-mail
# services as of 2026-07. It is NOT exhaustive -- new disposable-mail
# domains appear constantly -- so this is a "block the obvious/common
# ones" measure, not a complete anti-abuse solution. It should be paired
# with the existing per-IP free-trial limiting (see api/public_demo.py)
# which doesn't depend on email at all.
#
# Maintenance: if abuse patterns show a specific domain being used to farm
# accounts, add it to DISPOSABLE_EMAIL_DOMAINS below.

DISPOSABLE_EMAIL_DOMAINS = frozenset({
    # 10minutemail family
    "10minutemail.com", "10minutemail.net", "10minemail.com", "10minutemail.co.za",
    "20minutemail.com", "temp10minutemail.com",
    # mailinator family
    "mailinator.com", "mailinator.net", "mailinator2.com", "sogetthis.com",
    "mailin8r.com", "mailinater.com", "notmailinator.com",
    # guerrillamail family
    "guerrillamail.com", "guerrillamail.net", "guerrillamail.org", "guerrillamail.biz",
    "guerrillamail.de", "guerrillamailblock.com", "sharklasers.com", "grr.la",
    "pokemail.net", "spam4.me",
    # temp-mail family
    "temp-mail.org", "tempmail.com", "tempmail.net", "temp-mail.io", "tempmailo.com",
    "tempmail.dev", "tmpmail.org", "tmpmail.net", "tmpeml.com", "tempmailaddress.com",
    "tempinbox.com", "throwawaymail.com", "trashmail.com", "trashmail.net",
    "trashmail.me", "trash-mail.com", "trashmail.io", "trashmail.ws",
    # mail drop / discard style
    "maildrop.cc", "mailnesia.com", "mailcatch.com", "mailnull.com",
    "getnada.com", "getairmail.com", "mytemp.email", "emailondeck.com",
    "throwawaymail.com", "dropmail.me", "moakt.com", "moakt.cc",
    # yopmail family
    "yopmail.com", "yopmail.fr", "yopmail.net", "cool.fr.nf", "jetable.fr.nf",
    "courriel.fr.nf", "moncourrier.fr.nf", "monemail.fr.nf", "monmail.fr.nf",
    # fake inbox / burner
    "fakeinbox.com", "fakemailgenerator.com", "burnermail.io", "emailfake.com",
    "email-fake.com", "fake-mail.net", "spamgourmet.com", "spambog.com",
    "spamex.com", "mytrashmail.com", "mt2015.com", "mt2014.com",
    # anonymous / disposable-focused providers
    "anonbox.net", "anonymbox.com", "incognitomail.com", "incognitomail.org",
    "mintemail.com", "mohmal.com", "mohmal.in", "mohmal.im", "mohmal.tech",
    "nada.email", "nwldx.com", "wegwerfemail.de", "wegwerfmail.de",
    "wegwerfmail.net", "wegwerfmail.org", "einrot.com", "einrot.de",
    "spoofmail.de", "objectmail.com", "proxymail.eu", "rcpt.at",
    "tafmail.com", "tempemail.co", "tempemail.net", "instant-mail.de",
    "byom.de", "dispostable.com", "discardmail.com", "discardmail.de",
    "no-spam.ws", "noclickemail.com", "spamfree24.org", "spamfree24.de",
    "kasmail.com", "luxusmail.org", "meltmail.com", "mailexpire.com",
    "mailslurp.com", "mailslurp.net", "mailslurp.biz", "1secmail.com",
    "1secmail.net", "1secmail.org", "33mail.com", "harakirimail.com",
    "kurzepost.de", "shitmail.me", "shitmail.org", "chogmail.com",
})


def is_disposable_email(email: str) -> bool:
    """Return True if the email's domain is a known disposable/temp-mail
    provider. Case-insensitive; ignores leading/trailing whitespace."""
    if not email or "@" not in email:
        return False
    domain = email.strip().rsplit("@", 1)[-1].strip().lower()
    return domain in DISPOSABLE_EMAIL_DOMAINS
