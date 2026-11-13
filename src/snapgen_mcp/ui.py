"""Inline views (MCP Apps) that hosts such as Claude render next to a tool result.

- result view: shows the finished images / videos of get_generation instead of bare links.
- upload view: a file picker that sends the file straight to this server's /upload/{id} endpoint.

Hosts without MCP Apps support ignore these and use the normal JSON result, which still has every URL.
Both views speak the small part of the MCP Apps postMessage protocol they need (ui/initialize, tool-result,
size-changed, open-link, message), so they load no external script.
"""
from __future__ import annotations

MIME = "text/html;profile=mcp-app"
RESULT_URI = "ui://snapgen/result.html"
UPLOAD_URI = "ui://snapgen/upload.html"

# SnapGen wordmark (from snapgen.ai, 259x40 WebP), inlined so the view loads no outside image for it.
LOGO_DATA_URI = (
    "data:image/webp;base64,"
    "UklGRqwZAABXRUJQVlA4WAoAAAAQAAAAAgEAJwAAQUxQSPIMAAAB8Mf//yol/v89zhTM0AMiaStgrZK76pbd/VpbAdfu7u5O2HDD2kZs3TW2bF"
    "/uCiaNsmKANAzDxLn/cZ7necaXvNx/I2ICiF8bfsCWNkxP8u6j7xZubUL/qt0/zgdQfiCYJYT+YAPs94f+m3IeUABp5X53RsNDYN7r+C+qSTLY"
    "WR9J9MPNLNNh/b+nqDSZgpWSOishe7OZ49TuPl76Wk3QGgw64f+IEJMpU7hW4rta7nYrB6kbzzn/6PmT1C96Gmopr47Lj6dmZN79ZXPvOrWBds"
    "iylat6u/OpRy1bsaqvMw+FXZDJmyRxHWdnWc/7OsZ7Vi7YlcdjaqOgmbfMkLU8XB36+kWlArgTyaf70wocNHJ5Tq9hPegkEd66xKr4TO2QoAQb"
    "5MU7PWsdlwF/WMH/sLfhNRPWvQRgm+HBd84CfOnFRX6brIzUaAnpOqYySneRI31XAYBYkfMcAOxXQmqZgDUFYNqqzXYGimYaX6/QGyIAnA9T9o"
    "UC8hzxaw2Ah10ZpA7dlQeg8iu1A4S3MwE8X9vcLSg+FUDBqtolaEcFAJSem/NeWGiHySeKAKByttdrNe8ZpKV9dYr2KSFyG3wVeDqbRaQO3fYS"
    "9t+DHOA2zgY8mycQkbbbM8ByxlibeCwrBlB9souBmM4dj5kAFA/Vv0Z+560MfBr86oiCd9TUnDDKEOl7pyB3jAP8twG23wNJ2ugbAH8351G7ex"
    "v1ygSD0dtV4xiVwdvHVc0jDH0AoHC9P3H6ry8CcCtc4NF4envpHGIwehtUDoh7BJQ8qAQev6v6H6CA7banszlI3e6W5UJDZQ0PAeYkPcN7ZkZ6"
    "2onW5NRh165tI53CV1/Oe55/Z38nDx5tq9nH0589yzm3qI0ucNzePSujiFovSkicE6JqOjU5/fnznAvLo/QyjQ8CKNvkS9y+a6tFEat9ZYy9d1"
    "3Je5af+s0YfxWr3qK9iUuCgsclPcx/nnlselONAo8kM5A8NAXAKl8HqUMWunJQ4++RN16QI+eBRVU/NVBU/2tAvBbKII1er3dSk9skwHRxQxHY"
    "FYfbyjXZ+hSyz9Z1/xHIHkU06A7w57D5uZB9ua81QxidBdgPNyOF7m2jo2NCnRmqAVfMkE2bYmREpQIZW1KsYOdNM/INzARq4t33VQB3IwXHeO"
    "4u6MOj6fQEL9b4yVHQXtRc6aFW4L0YQPnXfgxZt/EiRAt4T0ex3jtnB2f1rXsi0ocR9b8N5GdUgPd6TxUR1d1tA+5/RK9Qu+gZeG37GkgiUgCr"
    "CM7qBd48TgcqgeutaXAmYJvp6RDN+8XmZCcOCv4MsKRtek/H0nR9AZSfHhvMpelaAMB8NTaQx3W8HVKxKifrpcSy20/yzs+Qmp5kPKkGW45pfZ"
    "nzxCTBjZ5E9PbPgLi/4StQzX0KAAV/nvj1sRUAvqovI7U8zXxiAYDCXjqO9+8BWOVLxtMW4GILBV9IhKbXgbIFPPrhJgAo/dyfQc1OAYD1Vh8e"
    "qrcPUtvjQ0MCZNxYL7a0dHNtPPcxgNv9iMh/txlA/p723gafzoeKlFWeHlLPxTt6Qw4AJLUkGnwXKJ6newWDMgH8szxEQ0LdCQ/sgG2OF1E461"
    "RvXxefPldqACQEyam2FQOF3bVEs/MB01A93z4vInX4nwBQNlEnJ0RnSlCW6MSou14CpL7HI4QdkQCw5uxur5K4jhcB5IwhqWFoOVAyT0equGwA"
    "1/o5kdRlzF0luXN9SKrq+KsIvJipE8bnA5kjyfHBF6zAjY46YrY5XwPcixFYtj2BJA25YAHSogWZxldE4HBDImpy1Q5810iRYVQOmCVfNJehFn"
    "8ykNKG4TGDVf6JmoOo7pI8BoCiHQFyJdsFBgWfA+wJftTwAIBbfUhWPTpTLgXA8zkGku34B4AjrdVTXwB/92XoImPj4+Ji4+Li4uPj4+Pixv6n"
    "Ds3IB/K6aEg2+pYIzPWiCMnllsSOfQSYBjvLTHsCVA1xJiJhbSFQ1FPL0v5iAb7wGvBfyIv561xZTY+xsgYz3KeyrGe8uEgTsiZNZMCUVE9iB9"
    "J6ENtltw34NoR63QTKlrrIkf9eC494sCnJa2cWAA8+YvzVh+Gx2QaFudHO35mATX7EufwFcLQpa7mPTMgNEZjszqpz1gJcDCPpu/cA7ApUMP4R"
    "B8r3ebKa/6bAY5qDiASffl8+kqB8n4Eh3mgmo1lWDiS1EsY/AW70JN4xOUCazPOpag567yJQNFs7Lh/IGslwX1etJC280TUR4m+fJyQkJCQmJC"
    "Qk7v25FLgXTuEpQM1Ig4z78RpglidreDZgmeTOcP7OBGS2E/gEv4WFrMpj7dXEDr/PSo1g+K5hlSeqlRCROnjGfQC435Hcxtthu+gno5pdBCS1"
    "dFpUChxtw9XpEpA2lHW7H/E2PABUr3Mf8gAonqeTeGyxKbneKuYOHPmisyYiBSjppZVx/s7Eof/WBJj/SE4+mpyc/NN9M2Cf6sHQnbMA+7yItB"
    "1TJRUL3EnWqX85o3K/gdH0KOtBZ3Ko6q2TAApWkavkV445klb6peXAoSZcb/8MpA0j6n8buNSJK+AzoGaLZ7tzgHiwiUTfd1dCQkJiQkLC3j3H"
    "igEcbtj+rkMKuzCKezimexqUnw9jaH+xAF94EZGq1T2gfK1A8n4bITUdbUpS1Xt5EvvDUQKHVq/XOwkMUnXIBUyHdA7SzSsGTkZwdbsKpMvcGc"
    "jV5DBgWudWd48NyB4tkNIZTwBxhkdUKmDLS5fPyMzIyMj4va3wCrSflTvAPNqghHS9q2pOuxBnxB1AfP7DCCMx66wAUH1zaQhx+sxLT0s71pxF"
    "IacA8xEXRbMlLSnuEXB3EI9qQj5P8TwdT6dLQOFMjTAmB0ByayUBf9qA7PaqoD/sqBnrrZc1GHRajVYnUHgKUNRDI/ctR3QKANjssjY7AHzfWB"
    "F5f1c4gDh9looo/iyEZFXt0mD9e4QrcfssAZDeSybsHFB1WOc2XlT2U0vqegUwb/PhaHLIzoNjbTlclpQCqQOJQr8HULXVl89ldgWAzX6k+bwC"
    "2N+AOAOaNgupo2EU99DyzZYI618C1hXvhEdEREREhoe3iT5RDRR21yrSdtjrzqHt9g/yZ+tIPnA3zGfCSKF+mBko2sRSd3wKFG0kRXNZ9b4Qge"
    "w4rYzr/AJwVWysIyP0vw3g22ZEmvF5AArW+vF4zX4M4G6MimhEDlA2ykXuneumatNk91fQ7JoI/PUW8Y7KBbAjgIh0XPxC+CW8WK4meeOcCusf"
    "YaS47S0AWSMFIhJanQGQOYjcJiiYwxKGPwSQNcuHEbwmH3wo+TSU4ToqFUDuWDUR+awvA2A6P9iL5dL5p1IABUMNROT5UzXweKw76/1LFuB6G4"
    "EiFDhJZkkWPgPEpT5cdX+2AtkdBCLdOQvwpQPUEedgveBP8sbZFXg8npQbF4oAChO7hEXO/BuA9YKfsrmSFkQ+W6sBVF2cHBPafsEtCzhSJBDT"
    "N3VrGRl3tASA7Yv6JK2faAIA019b/tOhff8lF8sAoGyKB0k7pAKoTupbV+/Rdt0TANXj3YhR4oig32zAsw/UXDT3KYDlBiLtLxbgC2WuH6UCL5"
    "aTrKpxohn2Sw0cQK0vQWqvroE0awg5jiJOgmk1WyGbNpQDgL3GBuaZGGLX31YCxQUTPYk9JhcAbM/SH5sBwL7Fn2R6OmBMLoDvGhF/8xsicMvP"
    "US7djpgAZAyQ8V9wH0DVfq0jdF3uSmT/maomchsvwnaRY3YR8KOEopJrJOyKK3eAtGFEA1KAotxycJqPRJK8x7gHSnL6GUg+Phu85Wv8yBHfmI"
    "DZnuR0oAqoHqFXoNpZAlj76Uh3zgF1llRAercdQx35K6SlO8mhmrY/mGTMl/sJROQ2ERAvcywoA5JaSihoUZYokzuvYxKQOZKV8vHUNBkxc34g"
    "cTffnCPKiY93viUQb/S3ZTK2y/1dSRqZCpj6cPxkBuZ4UZcHAP5sQUo7PQBwypd0f1iB/UYut4+rwHzQiRF2FszyRMEhRIb2K36+n/nwt63djS"
    "TVhsTFxXbXywgtR8bFf+jJICF4WMKlh2k39o9tojJ2josb2IiofwpwZyDVG/XF9Yz0q/tG1SOlQmDfVcl/Z2TcPrFhYLBACrVtpx2+mX733Kbu"
    "HsT26RsbPzJIJaN+f1RcfAsdtRoaGxsfqVek7x4bGz/Ug1RdY2Pj2uu4Qs+C/SheYhhjZZmPujmIiAQng7OK/lfVznoNcTMGERFp9HoNOVqrN2"
    "jI0Rq9TqDaVojJlClYIfFZBrZ4taHjXu8BKcBdxhuk8DbHKkmdFXLXG9ded940KPSsTPZwiX5kDav6e33tdfeNw2V0OcP0g1FCTY+wMvpS7dxf"
    "MvhNg4xzSgBUJTUjpjrivCR3oqq2ug3xDYT0nS/g+XJPkq+7tKQyuQ3V1l4to6JbGt8IAFZQOCCUDAAA8DQAnQEqAwEoAD4xFIhCoiEhFfjfXC"
    "ADBLYG3gJcb68+fqf5VeyBXH6v+FePLqTykOWv9P/ePy4+bX+L/xX9J9zv6F/0PuC/pt+wXrLf6r2Vf1n0C/z/+0/9//S+77/n/2A9yv7TewB/"
    "O/79/9/ac/3fsVft57AH8q/0Hq1/8P9p/gn/cT9vvgb/Xr/3dYB/6uJT/t3b98qucpD628e2GXbch/pfFH9hddIoAfwT+ef5fl6agX8X/pH+76"
    "8X7k+wB+noxSur5QqDQxPeUH7IM7YHp5yMAhbFtY9IdkXqMAsV/XffOT4ZGW1vOb3/H176hdo7nqtX1BP3z9nKQ4gPdkPu+8P7pAUjW+17uPhQ"
    "dRYGA4RSWSnKwTmgSgxlEvC187896uEAaQ50V3RDLumZcq6HYCr40qfQAS86W2cMb44ldJ0+OMwsAlrw/BQVfUIRLI+j1CFfNJXW1vrRIFqQsM"
    "Ed2IRs5zALTYKXFy3CsC+vC8scKTDGyEWaEgvJahtOBqteBsfTxL6OMjEaspBsnsVu/n95slxz3beF7M8Qvh259xPgjG/AqgMBlCpiIhj0AP7/"
    "wyAD1hwMX0F8wGxizvVaz3IjZYMoGUX9yG76Dv4qtHSEyzJB6u1fkxOde3bilAEVFl+C8j1+pZ3/VL48C1+Gkg+rDtjK3u2+WX08Nh+F9DUmgK"
    "9+9F0FKlBBaAUVcaP2t4CYl8LCie1n4pQoeDFsYPArxU6ridV3IPcZjEOeImN1p7m+fBgxbg2jGA7wfAdPknaZ/ZrEuvEKRfrhNqcT+zo3CQmY"
    "/gpFcsq6KclsB0OWBSTjpvxluBtdYnYlGbQAcylteGACjV+5pe1SfNjqtpdbE+DipAEBV2qi9Y/iIW6wVZFm7BaX9CwHrSko/0tvxPK4YrXuXH"
    "69p9KnML5/CXiP0Dbn70Q4/SNY9bUmFZWVv1q3NkRyOMG3Wlh++ai1CJTwNioefkoDp5Z143/wxH5HTv+sT95eRYeU5ujd7hZt4RIFpWxiBIZM"
    "B6ljrcEHN0TPW7tJDWKz7Ge9gWTDkZFQximNg9pszEaOENvuFCyDcg9PetaKFN87xeDj5chT/jnIx/5Bw4xxfQzi0sas4MIFdyVACJR5PdZGo8"
    "vb9KQIkwFniugG+tub60d/BjOAt0mDgWlxYrdAXkU9uqBGi06B5te+CN3rz9Sngmx4GL5SqgUkUm3uQxxvI2b+btGjPr86n/LmkKFKGfJjwpX+"
    "Y3ABwNDkOuemG2S4lJKRpNVsFirhrP9rtPVfl8+oG86UIF5dj3PBBrqAN4qU971HxhZxOk1Xtc+jYI4Q/t/37p35yBbCIwYlmQQAoVShj+D6HZ"
    "2TvmXjlGXhqcxrlN96PQjEe46fX0TXXj0rJwxQqFYr32/iPOVI3sMxQ/DD4mfi9Je3voC0EDpecn/+PQoIAeuRG/My9zAnD9I0XiW3WNPR6brD"
    "OFZtrZERmVZ6jZdX2ygsSNXD0m0d7rI1iRIHli00FF3MenznL0MW0RO25dVeplV8djt6RJ0hELm9TnIecojXpCAvdw8ln4dNeFWVijeN6XU0Sm"
    "UveaRdkGSFvfEys1Dsdj+1bAxWIFsFQdIg3fnk+OR7vQL/Jh3vjzU/8KDFm7afDRnK7Sd//zWzYSNJ0fAYGC2y/c/8Tpf/5mgAfq+4pxAijQu7"
    "U/wh34POPzbAob7DUobDOJqBFwvHOGMlLJHzevFgNk0tMCXH+u+XseB4v8ZLpl/5KTvXiXl+AKdsrQq+XxRUdOLwozHsiD0vNlI6PeGGDL7/yf"
    "KyD8E8m4YFjFYoQnj15tUtedOBV8QhBsifqeRo104f/4/f+7QIIJk8zp9Px3cxjKuDbzhXikKkMwCTKz90Ds//zFSscPDZGibHx3YPz0r4QlMi"
    "M10I/0EhEJF2i5DAiect4ghDRtoundVic08KBof8iYnL666uq1DOSbuCpkuGeYuGmHos+O2nTHJR/HGV2ZUEm5v1J/OO35grdyTMbxicHD+W6n"
    "nYzEPEouivX7KjIgNsMPs7n0ewYrqQzfw0A0u1s6kcKf4LvMwbJKdLYSsfM1WN84/9gh8KQZ8ERIMHyR9Wqk//FsDp56UjS5TvpGKabBLS271A"
    "5QFw8WIB+16ORWpjjfGAveJYlOTfqlE7sbU0zIRJyXH8/BwJsa3eCZmN2f0uYMRJzQRf+ymuWrT8rE45vqiaBqOB8kvXzlBOMtD9+Y5IUkz2sJ"
    "2BEUzDoRcM0KgAZNENc4PVHdyApMioWdC1GB25JbiGKAXl0EmsaCzb2R4yNGtOCGbC0qPb1BYfkL7p7bJU0yF3YnwgzdkdBCioZz/aE2oZmKBg"
    "GhPOupwOjqPzFOcMwIPKKQrz6vy7j6BckWtV4rCno+PeM75NICnRZKvS14nEg+4LLpsOrl3EH1nAvEsudRLeJemEC2uaJNAHl+FyPcOyMz2VTR"
    "/dqiM8Z7o98i8QVM/mP/Dt6YscMGgVnFmVlDnwc7HOYUmBLVoSNETnYDxEDbTgSo4Cwno1yfSZRD+UC3ksuRtTKHFqSPKHGzsz3seI0wOoF4Yy"
    "FNWLSiOXzLvBxkjaGCBlsqgBO53X3zEKCxCSxDBuWAhYPrbDjpE9RzI9zVtI2FzB101ZHbyJuUjaE87l07dxXnL8HL26tSUaffma9bHnKkrVZF"
    "ET6d+jIuBBk8ugj8xMa3awzAlgskBMkMLQ/6O9hip+m9bu4BcCsYW/K9YrnXj+5fO2hp0A1VCfzHHHw3onuKYz5Gv1k3qLvflWuc69Fw1miH4r"
    "fey/NCTFWF02osNWwUIrxYQ/Okc5tHEwq45eIlldf3rx7uAYgBro1vBec20nDxNIGIclIQGcd+988JlIBrKBNrsohR+K0YUEi5Li1Vji2F43bo"
    "zbiZ5eiqN+PWXyLWr4ckNhFcoBnpxkYjQ+IUf1O6iBewfp1MK4fSG1dsroGUREcVY2d1TPbEyVtg4asK53rg6ofe7M1pvyrHrwKhEdSFbt1ByY"
    "po63of9X4zcr8qH70m4k4A8a5WJcOGHwCsq7tNgbaIcjoPoXMFO8l+ygsK2oKO0qD0OExxfvNduZn+7WxdooPfSceq0Ewo/OZkq/HiNMWshCDt"
    "3L7ycOvvlZ0Nxk/TRUmzIOR4pR3QEoKce6ueV2W6hzFyePmRTfRVoR2mmgzppX+oYab2q/TODReDQliApLJ7T0bDJvuRIxJbZ/v7bNzn4oa09w"
    "q2HqGG0Jf3Tt1gk/yTv89z6tbAUJy4P5qzMU1VGne1crkAqUTMJNUtv4lB+zcZiWOa6xzcK1g2d3nwf4K64sY8vTyvbpjGFPVZQmuZR6kIfG1q"
    "OlxaSqhFSywWlgwg4+pNQAdvJK/3fLX+xnirx+TwFoVDrQeJlxyv6vhuUbgTFMGmwmeuzs1Nv00KDylLqvo3CQWj0T9mdiLp8OfUB/EzNLCmhY"
    "3K+w8HZpebgwfcJamoMYLOK/CEKAN4FnBkufDmxdDQ1f8z42X5pzEZHiVJyA/g+F/Q297MV7KkhynFQnZs+kXbklLdX7K6Z/dkLU4NOQk54J7/"
    "dTOP6DYZTij6LFn/9PDeTdq0o/f+ZcNYT8q7/7aHTf255XDztbyRH6ZG0Oly3UWBG/jthHMRIvqQPTbv6q1Sq6AssoXsQ+RMsXJhEKi3DoYgc0"
    "eA7YN/6xqwRqw88ENfruQQzIV6Vg4KYG//x3P2KpehBoqFhf7x0xYdu6UtZEHoB1Yu2pyrbrH76Lmb5X//6uvVeNDbbOAVUKOWi3M+0kziN+8C"
    "3KspuQgFyKjQQnE2PvbJ4bKmW0BfizZ+1Lk9XWF3t2x5+XAdRjA2vCgLgGBDFe08UmwnxcOv/8ocOP2bZ3VO4Phev6vBhZNKq7u4hUgiCTVfOU"
    "d+uHUSBkANeGqBSChMKZMEm46ZsSlZNQe9x1f2fCuQdvLV/M9Ws2m2WtvkK4uiM/pBQ8rpq0pee8xuvdTP8YFeuGh7mP8qe7CJt3NDAEf4xq0g"
    "gXcRQMI+pH9ICA3WOMIMad6Jb9XqC//rXHUJ0G7REYcmhEztQG5uIUajKELMGcWNxJP9NPlkl3ZNyJm1raoyAkteiFs7qZ+g51BA81TjkpcWWF"
    "1fF4Cty8kp+c7BaXgGfmW1M1w1xyp9f54//x1VvXDzgVF8ylq89fRUubwkYvrj3usKVNSRWgN1a8ZEv/4Zv//9BiTFrOzWkvONo5Dtv5OT264K"
    "Od6FIcGis2VbVR+Jx5rbnfrTEXA1ts7cO8JCdCxQo9f1GEsfl4qkflYilMJnUJt0aByob61woWX6RZfgAAAA=="
)

_BRIDGE = r"""
<script>
const bridge = (() => {
  let nextId = 1; const pending = new Map(); const handlers = {};
  window.addEventListener('message', (e) => {
    const m = e.data; if (!m || m.jsonrpc !== '2.0') return;
    if (m.id !== undefined && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.reject(m.error) : p.resolve(m.result); return; }
    if (m.method && handlers[m.method]) handlers[m.method](m.params || {});
  });
  const post = (msg) => window.parent.postMessage({ jsonrpc: '2.0', ...msg }, '*');
  const request = (method, params) => new Promise((resolve, reject) => { const id = nextId++; pending.set(id, { resolve, reject }); post({ id, method, params }); });
  const notify = (method, params) => post({ method, params });
  const on = (method, fn) => { handlers[method] = fn; };
  // Đo theo nội dung (body), không theo documentElement: documentElement luôn cao ít nhất bằng iframe nên chỉ tăng không giảm
  const resize = () => { const r = document.body.getBoundingClientRect(); notify('ui/notifications/size-changed', { width: Math.ceil(r.width), height: Math.ceil(r.height) }); };
  new ResizeObserver(resize).observe(document.body);
  const ready = request('ui/initialize', { protocolVersion: '2026-01-26', appInfo: { name: 'snapgen', version: '1' }, appCapabilities: {} })
    .then((r) => { const t = r && r.hostContext && r.hostContext.theme; if (t) document.documentElement.dataset.theme = t; notify('ui/notifications/initialized', {}); return r; })
    .catch(() => null);
  // A tool result's JSON, from structuredContent or from the first text block.
  const payload = (result) => {
    if (!result) return null;
    let v = result.structuredContent;
    if (v && typeof v === 'object' && 'result' in v && Object.keys(v).length === 1) v = v.result;
    if (v) return v;
    const text = (result.content || []).find((c) => c.type === 'text');
    try { return text ? JSON.parse(text.text) : null; } catch { return null; }
  };
  const openLink = (url) => request('ui/open-link', { url }).catch(() => window.open(url, '_blank'));
  const say = (text) => request('ui/message', { role: 'user', content: [{ type: 'text', text }] }).catch(() => null);
  return { on, ready, payload, openLink, say, resize };
})();
</script>
"""

_STYLE = """
<style>
:root { --bg: transparent; --fg: #1a1a1a; --muted: #6b6b6b; --line: #e3e3e3; --accent: #c2549a; --card: #fafafa; }
:root[data-theme="dark"] { --fg: #ececec; --muted: #a0a0a0; --line: #333; --card: #1f1f1f; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --fg: #ececec; --muted: #a0a0a0; --line: #333; --card: #1f1f1f; } }
* { box-sizing: border-box; }
body { margin: 0; padding: 12px; background: var(--bg); color: var(--fg); font: 14px/1.45 system-ui, -apple-system, Segoe UI, sans-serif; }
.muted { color: var(--muted); font-size: 12px; }
.grid { display: grid; gap: 8px; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); }
.item { border: 1px solid var(--line); border-radius: 10px; overflow: hidden; background: var(--card); }
.item img, .item video { display: block; width: 100%; height: auto; max-height: 520px; object-fit: contain; background: #000; }
.bar { display: flex; justify-content: space-between; align-items: center; gap: 8px; padding: 6px 10px; }
a, button.link { color: var(--accent); background: none; border: 0; padding: 0; cursor: pointer; font: inherit; text-decoration: none; }
.status { padding: 10px 12px; border: 1px solid var(--line); border-radius: 10px; background: var(--card); }
.drop { border: 2px dashed var(--line); border-radius: 12px; padding: 22px; text-align: center; cursor: pointer; }
.drop.over { border-color: var(--accent); }
.btn { background: var(--accent); color: #fff; border: 0; border-radius: 8px; padding: 8px 14px; cursor: pointer; font: inherit; }
.btn[disabled] { opacity: .5; cursor: default; }
progress { width: 100%; accent-color: var(--accent); }
.head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 10px; }
.head img { height: 20px; width: auto; display: block; }
.head .muted { text-align: right; }
</style>
"""

RESULT_HTML = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
{_STYLE}</head><body><div class="head"><img src="{LOGO_DATA_URI}" alt="SnapGen"><span id="meta" class="muted"></span></div><div id="root" class="muted">Waiting for the result…</div>{_BRIDGE}
<script>
const root = document.getElementById('root'), meta = document.getElementById('meta');
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
function render(r) {{
  if (!r) return;
  meta.textContent = [r.model, r.credits_used != null ? r.credits_used + ' credits' : ''].filter(Boolean).join(' · ');
  if (r.failed) {{ root.className = 'status'; root.innerHTML = '<b>Generation failed.</b> ' + esc(r.error || ''); return; }}
  if (!r.done) {{ root.className = 'status'; root.innerHTML = 'Still generating' + (r.progress_percent ? ' (' + esc(r.progress_percent) + '%)' : '') + '…'; return; }}
  const media = [...(r.image_urls || []).map((u) => ['img', u]), ...(r.video_urls || []).map((u) => ['video', u])];
  root.className = '';
  root.innerHTML = '<div class="grid">' + media.map(([kind, url], i) =>
    '<div class="item">' + (kind === 'img' ? '<img src="' + esc(url) + '" alt="Generated image ' + (i + 1) + '">' : '<video src="' + esc(url) + '" controls playsinline preload="metadata"></video>') +
    '<div class="bar"><span class="muted">' + (kind === 'img' ? 'Image' : 'Video') + ' ' + (i + 1) + '</span><button class="link" data-url="' + esc(url) + '">Open</button></div></div>').join('') + '</div><div class="muted" style="margin-top:8px">Links expire. Download what you want to keep.</div>';
  root.querySelectorAll('button[data-url]').forEach((b) => b.onclick = () => bridge.openLink(b.dataset.url));
}}
bridge.on('ui/notifications/tool-result', (p) => render(bridge.payload(p)));
</script></body></html>"""

UPLOAD_HTML = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
{_STYLE}</head><body>
<div class="head"><img src="{LOGO_DATA_URI}" alt="SnapGen"><span class="muted">Upload a reference file</span></div>
<div id="drop" class="drop"><b>Choose a file</b> or drop it here<div class="muted">Images up to 20 MB, videos up to 100 MB, audio up to 20 MB</div>
<input id="file" type="file" accept="image/*,video/*,audio/*" hidden></div>
<div id="state" class="muted" style="margin-top:8px"></div>
{_BRIDGE}
<script>
const drop = document.getElementById('drop'), input = document.getElementById('file'), state = document.getElementById('state');
// The standalone page gets its target from the server; the inline view gets it from the upload_media result.
let target = window.SNAPGEN_UPLOAD || null;
bridge.on('ui/notifications/tool-result', (p) => {{ const r = bridge.payload(p); if (r && r.upload_url) target = r; }});
drop.onclick = () => input.click();
drop.ondragover = (e) => {{ e.preventDefault(); drop.classList.add('over'); }};
drop.ondragleave = () => drop.classList.remove('over');
drop.ondrop = (e) => {{ e.preventDefault(); drop.classList.remove('over'); if (e.dataTransfer.files[0]) send(e.dataTransfer.files[0]); }};
input.onchange = () => input.files[0] && send(input.files[0]);
function send(file) {{
  if (!target) {{ state.textContent = 'This upload link is not ready yet. Ask for a new one.'; return; }}
  const form = new FormData(); form.append('file', file);
  const xhr = new XMLHttpRequest();
  state.innerHTML = '<progress max="100" value="0"></progress>';
  xhr.upload.onprogress = (e) => {{ if (e.lengthComputable) state.firstChild.value = Math.round(e.loaded * 100 / e.total); }};
  xhr.onload = () => {{
    let body = {{}}; try {{ body = JSON.parse(xhr.responseText); }} catch {{}}
    if (xhr.status === 200) {{
      state.textContent = 'Uploaded ' + file.name + '. You can go back to the chat.';
      drop.style.display = 'none';
      bridge.say('I uploaded ' + file.name + ' (upload_id ' + target.upload_id + '). Use it as the reference.');
    }} else {{ state.textContent = body.error_description || ('Upload failed (' + xhr.status + ').'); }}
  }};
  xhr.onerror = () => {{ state.textContent = 'Upload failed: network error.'; }};
  xhr.open('POST', target.upload_url); xhr.send(form);
}}
</script></body></html>"""


def standalone_upload_page(upload_id: str, upload_url: str) -> str:
    """The upload view as a normal web page, for clients that only show the link."""
    import json

    inject = f"<script>window.SNAPGEN_UPLOAD = {json.dumps({'upload_id': upload_id, 'upload_url': upload_url})};</script>"
    page = UPLOAD_HTML.replace("<body>", "<body>" + inject, 1)
    return page.replace("<head>", "<head><title>SnapGen upload</title>", 1)
