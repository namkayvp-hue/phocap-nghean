from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
import subprocess
import sys
import traceback
import zipfile
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
VERSION = "BAI-13C-1-TH-M1-TU-DONG-V1"
ROUTER_REL = Path("app/routers/report_center.py")
TEMPLATE_HTML_REL = Path("app/templates/reports/report_center.html")
MAIN_REL = Path("app/main.py")
DB_REL = Path("data/phocap.db")
TEMPLATE_REL = Path("app/report_templates/pcgd_xmc_2025/PCGD_2025_TH_M1.xlsx")
MARKER_START = "# === BAI_13C_1_TH_M1_START ==="
MARKER_END = "# === BAI_13C_1_TH_M1_END ==="

TEMPLATE_B64 = "UEsDBBQABgAIAAAAIQB0NlqmegEAAIQFAAATAAgCW0NvbnRlbnRfVHlwZXNdLnhtbCCiBAIooAACAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACsVM1OAjEQvpv4DpteDVvwYIxh4YB6VBLwAWo7sA3dtukMCG/vbEFiDEIIXLbZtvP9TGemP1w3rlhBQht8JXplVxTgdTDWzyvxMX3tPIoCSXmjXPBQiQ2gGA5ub/rTTQQsONpjJWqi+CQl6hoahWWI4PlkFlKjiH/TXEalF2oO8r7bfZA6eAJPHWoxxKD/DDO1dFS8rHl7q+TTelGMtvdaqkqoGJ3VilioXHnzh6QTZjOrwQS9bBi6xJhAGawBqHFlTJYZ0wSI2BgKeZAzgcPzSHeuSo7MwrC2Ee/Y+j8M7cn/rnZx7/wcyRooxirRm2rYu1w7+RXS4jOERXkc5NzU5BSVjbL+R/cR/nwZZV56VxbS+svAJ3QQ1xjI/L1cQoY5QYi0cYDXTnsGPcVcqwRmQly986sL+I19QodWTo9qLpErJ2GPe4yfW3qcQkSeGgnOF/DTom10JzIQJLKwb9JDxb5n5JFzsWNoZ5oBc4Bb5hk6+AYAAP//AwBQSwMEFAAGAAgAAAAhALVVMCP0AAAATAIAAAsACAJfcmVscy8ucmVscyCiBAIooAACAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACskk1PwzAMhu9I/IfI99XdkBBCS3dBSLshVH6ASdwPtY2jJBvdvyccEFQagwNHf71+/Mrb3TyN6sgh9uI0rIsSFDsjtnethpf6cXUHKiZylkZxrOHEEXbV9dX2mUdKeSh2vY8qq7iooUvJ3yNG0/FEsRDPLlcaCROlHIYWPZmBWsZNWd5i+K4B1UJT7a2GsLc3oOqTz5t/15am6Q0/iDlM7NKZFchzYmfZrnzIbCH1+RpVU2g5abBinnI6InlfZGzA80SbvxP9fC1OnMhSIjQS+DLPR8cloPV/WrQ08cudecQ3CcOryPDJgosfqN4BAAD//wMAUEsDBBQABgAIAAAAIQBXdaOURgMAAMYHAAAPAAAAeGwvd29ya2Jvb2sueG1spFVNbts6EN4X6B0E7RWJ+rcQp4ilCA2QBEHqJhsDBS3RERFJVEkqdhB01XXvUKDLd4PXZU+Sm3QoWU5dFw9+qWGTJmf08ZuZb6jDN6uq1O4JF5TVYx0dWLpG6ozltL4d6++nqRHqmpC4znHJajLWH4jQ3xy9fnW4ZPxuztidBgC1GOuFlE1kmiIrSIXFAWtIDZYF4xWWsOS3pmg4wbkoCJFVadqW5ZsVprXeI0R8Hwy2WNCMJCxrK1LLHoSTEkugLwraiAGtyvaBqzC/axsjY1UDEHNaUvnQgepalUWntzXjeF5C2CvkaSsOXx9+yILBHk4C085RFc04E2whDwDa7EnvxI8sE6GtFKx2c7Afkmtyck9VDTesuP9CVv4Gy38GQ9ZfoyGQVqeVCJL3QjRvw83Wjw4XtCTXvXQ13DQXuFKVKnWtxEKe5FSSfKwHsGRLsrXB22bS0hKsjmXboW4ebeR8yWEBtT8uJeE1liRmtQSpran/raw67LhgIGLtinxsKSfQOyAhCAdGnEV4Li6xLLSWl2M9jmbvBUQ4a2GcJUTcSdbMJvTp++dWq57+/afdXkx7S/H0/Us2+0WgeLcb/odEcaYyZEJWeub9/98zBAHwaJDhpeQa/D9NzqAU7/A9FAbKn6/79hQyH354TCdJ6HuBbaS+nRhu7B0bk/TEMuI4iWMr9NBx4HyCKLgfZQy3slgXW2GOdRcqu2M6x6vBgqyopfnz+Y/W+mOo+bdhsH1Skapr7ZqSpXiWhVpqqxta52wJ12ToQzQP28tlZ7yhuSzAwx/Z4NLvvSX0tgDGyHI92JR4fqUuLNBmoFqM24roWH90nMRKnCQwvDhwDNcJHWNkO4HhjpLUDn3kBUHaETR/Ydjdp8C0m7W664Ep+/G11lY/vsHdra5blW9H13ikjuGnOerqOTyZ4TK75JqalCMaIcseKQ+ykmdCdjPIkQLDiRdOLGdkG26KUsNFI8uYTHzX8JLU8QKUxCceMBzaXCEuXtjpodk9TbBsoUVUd3TrSI3penezueg31tFvKTu6SlQo66f/y/EdvPJKsqdzer2nY3xxPj3f0/fsZPrhJu1q88doTSgI9N5QFnN4BR/9BAAA//8DAFBLAwQUAAYACAAAACEAkgeU7AQBAAA/AwAAGgAIAXhsL19yZWxzL3dvcmtib29rLnhtbC5yZWxzIKIEASigAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAArJLLasQwDEX3hf6D0b5xMn1QhnFm0VKYbZt+gHCUOExiB1t95O9rUjrJwJBusjFIwvceibvbf3et+CQfGmcVZEkKgqx2ZWNrBe/Fy80jiMBoS2ydJQUDBdjn11e7V2qR46dgmj6IqGKDAsPcb6UM2lCHIXE92TipnO+QY+lr2aM+Yk1yk6YP0s81ID/TFIdSgT+UtyCKoY/O/2u7qmo0PTv90ZHlCxYy8NDGBUSBviZW8FsnkRHkZfvNmvYcz0KT+1jK8c2WGLI1Gb6cPwZDxBPHqRXkOFmEuV8TRmOrnww2doI5tZYucrdqKAx6Kt/Yx8zPszFv/8HIs9jnPwAAAP//AwBQSwMEFAAGAAgAAAAhAKfJOUZGHQAAop8AABgAAAB4bC93b3Jrc2hlZXRzL3NoZWV0MS54bWy0nVtvG0l2x98D5DswBAJkMbHEbt5EwtJC4kW8k2NT7Jl540iUTYwkainaHu9in4MgT/kIizwHed953E/ib5JTXafYp86/2bKM6UUce3516tb1rzrVp7qbr//46/1d4eNq+7TePJwWg6NSsbB6uN7crB/enRav5t1XJ8XC0275cLO82zysToufV0/FP5798z+9/rTZ/vL0frXaFaiEh6fT4vvd7rF5fPx0/X51v3w62jyuHijldrO9X+7oP7fvjp8et6vlTZzp/u44LJVqx/fL9UPRltDcfk0Zm9vb9fWqvbn+cL962NlCtqu75Y7a//R+/fjkSru//pri7pfbXz48vrre3D9SET+v79a7z3GhxcL9dbP/7mGzXf58R/3+Nagsrwu/bun/QvpTdtXEHGq6X19vN0+b290RlXxs24zdbxw3jpfX+5Kw/19VTFA53q4+rs0AJkWF39akoLovK0wKK39jYbV9YeZybZsf1jenxb/UG42L89J5+Oq8Wq28qgS12qvz+kX9VXDeOi9fdEq1IKj9tXj2OtbJbHv2erf8ubW522wL23c/nxa79L8S/a94fPb6eG9zsyY5mEtQ2K5uT4vnQfN8WK8Zm9hksV59ehL/Ljy933z6aUVjdFokxVMNb1d3q+vdihoYFAtG2z9vNr+YbH1CJWrO4/JhVfj17SMp5LRYLRY+J//cbR5Hq9tda3V3R+2rFQvL693642pGOU6LP292u839m/W797t4Ju2I3W43f149xK2LqzXtNuWfFqkoNrVlcJnUpqc/xT3rBmnZbCWmEa5ym/GcGsMZ6Z/maqj6vNbJKqOKmfi2TvPv/dU218RdeXlZu/FEn20LN6vb5Ye7HQ1ZtL7ZvT8tnhzV6XoxfrP51FuZi0EXunpEPJ5AzZvP7dXTNc1outhH5aqp7npzR0NG/79wvzZLE83I5a+nRZLSJ1tu+Sik/E+7z2Z+Vij9+sMTXWquNb5O+9wVzk1/c+5G3Kqvy03VxHXT35w7PCqXw1I5EC2gS53RAEqNi6C/uYiq1wBSYUbuOuemv/e5Rd+zM9NAxlUHSfNr2PxKdiGB64D5B7ehdnSiL8JzpbiOBA0xjElP6F8ZVyGkJsY9CRMRVF86EKGTghm6vZK+ugnuMoRyIEsnSgvP9MNdhTAZz4oU8zPZ3YCW6Xq8uAfl/UQyC52bSTCQ2U0ok3ewszGZUGUzm3k+PZPbzSea6N/eBDcS5eQivqAJ+0lRK58kfbBLFXeiHi96dhmKvUh7uVuevd5uPhXIVZslmdZsciBB01zTeEWrHNX2Xd8vc4fWOFrcTEHnpqTTYo3+otXviVzNx7Ny4/XxR1plr9nmYm9jFkaTqwWkDaTDhObavuSSXzC5k7jyRrzimoIvgfSA9IEMgAyBjICMgUyATC2pGzftLk/gd2K2NzFeisZnP0gk099pkExJapAqFTVIe5v9IAFpA+lYUveG/0SNEtuEySgB6QHpAxkAGQIZARkDmQCZWhLvE2J9zgTwhoSW7t9pSExJp8V6eX9RLoC0gLSBdJhU9uV0gVwC6QHpAxkAGQIZARkDmQCZWpLM2pkFgd0WyylAi5t3vc2CRWNj3azdtMWL2bevX6YGmhq0DO8naKhmBpsk8mgBaQPpWBIE8ZKo5nzXJlbitLAUqAXzUiWrCdVTyXW/vX2VXPOTByq56icPbbLZ9CYLum8yUiWolWSskst+7olKVld7qpL1apnSPFX/nMdiPyOuNFhoEGnwgwY/avCTBufnQC6AOOXs23bulJMQVk58x+MtPmaHIp327z8ZTA1qMih5XLCJmAxA2kA6lvBkUCPetYl2MiixXso0pfOeTFNTpC/T1OwayLRAbSmGNtHefce+YOSZKzmOvUTVsYmXqKbB1EtUEp5BK+Z8TRNRa7DQIBLA05G5rc5XR6YGpSM1sBdsInQEpA2kYwnrSF1RE7ugWisNu6pWKnpVtelVEw/5eBYGVTVcPT+9XFZj3ffTS3WtK063K35YKSlNDrl9IdV/e/b2avxv3VpzUPvD6+Nb06AgqGg/MPJ7FIaqxLHfovBEiXnip1cbeq31WxzU9GILLR7VmtN9ixuhzjDnEUtUqsFCg0gAT6XkkXNWqamBVEo3U3tPp5aYi73JflMMpA2kYwmrVE3trk2sGhXQoJdCNWaXnF6O009qav3tecmNksrd93OHasAHnGzX2kZVL342uRIrNL4o75fb1U3RhiWH9eawbOJq6zimGAu43hzUnYAr1aq6fCOvryd6woz9vlTVEjHxkoNSVV3Jqd8ZPV1nmZ2Z1Zsz1xmasKYzo3pzuu9MmYIi/r5lzuOcaFuDhQaRAJ62zVXMdwU2NagVWC0eF2wiVmAgbSAdS1jbSpxdm1itxtrVwubEml1+/Yvb8xK1qL1EteoPOLGets8e2kQUtNUwTeqPZ0p1I68Pav6MvZao1XKSlTj1mqk6OMtqZhwK/nimN7k8MokaNVhoEAngqZEiLDmr0dRAoXTakOxXWh0jYpN412tjRJY0ZGhBjVWbTZLIQseSwK6eyrxrE3mDoKbDpU3k3YG+4/ISVdP7XqL24QNOdbsCdbfFTTLtvZUrrhSoaszI60aod6R+a9QMnXipod6Tem0NVOosq62s0rqaMHObJxnVKw0WGkQCeDKl8EDeOo2rIKHGwdNYhRcOiWWSUZ0amgT11JRuu3xxTCMuqsMosN5X+coup/LGQI3bpUu1wtabAj9VxwP81EAJZuCSbbMClXvIyRWTfEiiFdWgkd8ZraSxapG+b1LJWqV+g1V7Z5ntdYupau+cMwmdAlkAiSTxpWpiul/t4MP4LM3GtL4+7m7DxidJFO2CnLJZZhuJ5FqMTuQiqgXQdkZiGWVEh27GReqALqeynwep2mZUraMHqXqpIFUvFaXKyezsQao2uWJa/fVS5TJtV1GqfotAqn4ySNVrMEg1q70HpWozSalqsuABSmwiSXypmlB3vntRE7HVm9FAB1mdkVxnOV+C2mjVYcQ7UuWbu5zqggJhXbt9NnBRgZI+vOopA7gJ7/sGQaOuA67OgLcAoTYYukbCfZfYBQQUb9C3V6pzpRNV81i1PajrLasyqOjLM1VtL9XUBZ5ltp01fHJS0ttXN5DJ/hXIAkgkia9ic4KQs4rtIcUJ/ZV4fTXfL2jjGUudlJsYqb63nJHcDgdqnWyzkXlgISlJjW/HGdldgY5ldjk5Eb8a/ks2cOJXY9vzk3U4LDN14FKt6HWgwbUsa98blktqkRi5/u5VMwYyATIFMsusnkWrb//dqAnF8mDvyQJsIkl8xZqzgZwVa48fSLEuenVBe89YnwlqOZQ4izajgMIXifbU4tNxRrxt1CdcnCwOfYH0gPSBDIAMmWRuSNXgjaCUMZAJkCmQWWbdh4QD51HukgvhwImUtPGFY8L6OQvHnhx4wuHDhOScuWWeyDJH2J5KlHttO6PEh3cY8d5SbwS6nJwo9BJID0gfyADIkEnm9hCEYzuZtGYM5U6ATIHMMus+JBw48+FSkqm6ABJJ4gvHRNpzFo4N5nvC4fi+5xGVo2kZL2d2iNke0Ro94xHZiD2iPiLiivgmW0coXarNTOfyyqDnG5R1nNJPVh594FLtggkekc9aMj1iCW+0ub/CI2oy4YrtM6XmKakpkBmTSmr1h/QJpz1uHMXCBuc90sbXp4mWO32ahyR///Nt49FMIFJ6RI7RS4/ISHpEi57xiGzEHlEf/HDl0iPaDAnpgU0fyADIkMnLPKKuewzlToBMgcwy6z4kHDhK4VLkwgaHKdLGF44JbOcsHBs794TD4XTpES16xiOykfSIFjmPqE9VApssPaImPbDpAxkAGTJ5mUfUdY+h3AmQKZBZZt2HhAOnHlyKFA6ce0gbXzgm1JyzcGw02xMOB7ilR9SHjS3ziPnzHtEaPeMR2Yg9oj4T4YoOeUQ+EbCZwR16qWHQUIX3XeHsUPUDEy6Zn4NTRyOcmu6S4hgnPcURhhAU4f4Kj6jJhIuWHtHZxKfy+gldm5jpHNX9z9wNoLhdhKMPsIkk8aRq3h7IWapxFb5zZFQTztEh4RwZZTtHZ5R+ytDlZPmMsOnxaVE4R7DpAxkAGTJ5kXOEUsZAJkCmQGaZdR9Y49wFToQDZAEkksQXjjyKyGdXFfJRhNhVMaoJ58go2zk6I+EcGTnnCA+X28qFc+QMCekB6QMZABkyeZFzhFLGQCZApkBmmXUfEg4cDLhRSLbjQCJJfOHIg4GchMOP2UvhcMzfc45qbW2FbJR5u8hG2c7RGbFz1KcHnHzAObrUdOfop+rgqUptVPSprDOw62VZP0vIyZnOMWjoBwJHrr+JcwQyATLdkzTnmNkSlqp2jm4AxRrHQyqkqkkkc/lSldH/nKS6j/7vY6lckeccOSIsnSPfyGbGUl2b3QsB+gUaW4Z0jpr0uIjEpg9kAGTI5GXOUdc9hnInQKZAZpl1H1rjdMj9yo2CEI62iaSNLxwZhM9JOBiENy9xmr29dI4WPeMc2Ug6R4vYOepngbpck3SONoN0jpr0IdcAyJDJy5yjrmkM5U6ATIHMMus+JBwIwrtREMKBILy08YUjg/A5CQeD8PH72iQczzmqM7KWM8p2jrbwZ5wjG/Hdm35tgys68LSnS7VPgeg7x8zUfmbqwKXah0DCsKzuOods8MyNo8428vuj78jHfqP0QXpm6tRvsn76M7O9rGf9JPfcDbNwofq4YAE2kSS+oOXhQE6CxsMB8x66WQnl/SUj6UI5op3tQtmIXagO/HNN0oXaDPL+UpM+5BoAGTJ5mQvVNY2h3AmQKZBZZt2HVkKI2rtRECshRO2ljS+c/KP25kMDKmrPyHOh1uoZF8pG0oVy1N4+/xXqqD3XJF2ozSBdqCZ9yDUAMmTyMheqaxpDuRMgUyCzzLoPCQei9m4UhHAgai9tfOHkH7UPMWrPyHeharFoOaNsF8pBe5oqhx/Q4ZLoKZD4nTMd2XfJ+wt4CaQHpA9kAGTIJNMH6rNuzlM94deSa/rFXmfAb9gFdVXCRBlU9JNuU3dl+R08fJwss90szJO6fpNo7soV3lAfAyzAJpLE12b+BwMhHgww8rwhx4ylN+RIdbY3ZCP2hjrozzVJb2gzSG+oSR9yDYAMmbzMG+qaxlDuBMgUyCyz7kOLmg7KX7lREIuatomkjScc81GbnMP0cRV+mJ6RFA6jwDx/lixP+umcvVVyK9pxjKWjX1PgZCEdID0gfSADIEMmL5IOlDIGMgEyBTLLrPuAdNxVT9YcIAsgkSS+dPIP1Jsv/ZiNVDLaF4wCerJ2/4qrMyPr5JsYyhe0nZF4acCVxTspHannZLGTAtID0gcyADJk8qKdFJQyBjIBMgUyy6z7kHIgUs+liGNsIJEkvnLyj9SbT2aZV0vkahLqT0M4IxHXYuQ92BXqt/jYyBzTH95JOaP0o+SuS052UkB6QPpABkCGTF60k4JSxkAmQKZAZpl1HxKXjptfuUFIPBqQSBJfXDK2br5W9vs/lVW2AduG/XCieUDtwiHxOiijmtgKMTKH5oefU3ZGfJCitqxdTpb+DGLrYNMHMgAyZPIyfwaxdSh3AmQKZJZZ9yHhQGzdXXIhHIitSxtfON4D7vkIxwZsG+J1zTIj8RoRI3pTLmsnxPnE65qcj2Pr+vMCXU6W7gxi62DTBzIAMmTyMncGsXUodwJkCmSWWfch4UBsnUuR7gxi69LGF473gHs+wuHIdsnzZ/rjH+YDj2a1I6tkb8RBVhkaQIfGGbMdmhddL+vouqtcODTOsCc9sOkDGQAZMnmZQ9N1j6HcCZApkFlm3YfkpePaV1yKlJe2iaSNLy8Z6c7JoXEsuiQ32shaZYx1M3rGpXmx7rKOdXMZ0qVBrBts+kAGQIZMXubSINYN5U6ATIHMMus+JB2IdbtLLlwaxLqljS8dGevOSTq83pXkZghZi2t/xqnZjOKF8I5rtb1HK+toNydLpwbRbrDpAxkAGTJ5mVODaDeUOwEyBTLLrPuQdCDazaXIVQei3dLGl46MduckHQ5Il2REWn8y7CL+6JFxasmmqZXC2nsmjkocs+90lnU0m5OTRe8SSA9IH8gAiP3sFH3azRwmH3qxX0ezoZQxkAmQKRD7lahDdR8SDzynzuVK8cBz6tLGF48MR+ckHg4Yl+QuOdQf6SknVsmOCFk7xa7jGH00w+XtMjMPryYfG9VvZaUaqfP3njOKByT+3ErfocQPDtBqiGiEaOxQsjBOEE0RzRDNGSVSuAKyABJJ4onDfLQ+ea0vl+1yXAVFf6Q29Ib1go0C++MW9hNOKaydwjrMzCFzogO9rWGjinnu4/aMXm7/rhuQ/4o/nkivAeh32525Oc0i80rpmD4G8a9s32gc1RqUJ2yUaqVqvaHXsp5rUbJK9h0SenIoWSOHmHHkUKLNsUPJ11smiKaIZojmjISegCyARJL4epJx6HwWG/NzF+bRfronTIZbf4/cGSUboRaiNqKOQ9li4k+vWDGNwpPvRma1s2Iq6ZPPSy6TfkrEiik4HgkxnRw1KtVypdGohvQDMOWaUm7PtUgsTozoNMAthgOHEqshZhwhGjskxcRXOEFTtJohmjOSYoKvy4BNJIkvJhmazklMNt7pi0mHpukLgLHipJgAtdGq41C2mGxRvDLRVyq+ow8O0J8a/anTnwaJq0R/QvpDaWGV/lAQnMXmP+x7yTXupRZKqZWOGlU6/g7r9dJJtVwu1U+0I3QNllrjnsqFi5HUGqARljV2SDhCRFNEM0RzRlJr8BQ42ESS+FrLP1JNMZP4GMRzhPrLxmzkO0KbUbJ2il2H2TOO0BbGcpvR2kVH3ywnfDbiksvcC6p8TB/tEY6wHtRK5ZOgVqnUS7UT/Q0Y1yKpJw5SSz1ZRKcIbjkbckaBRljWGNEE0RTRDNGckdSTDlcvwCaSxNfTSwLYYf1bPuJGgRQbYZRHrWUdh9xbiTPaFNZOYR1mzwjKNoMFNQyC72bm02vx+tTQ23Eu0W3DKpXjf6NvBFKO0h+cqEjm6vOurhlyO2UrpZc6Eg/Il8N8wmK/MdCfPBi6bpKVyzlKYeMUNklh0xQ2Y0aHG66KOSOpLh3TXoBNJImvLh3l5p+wIPzCLwFSSMWISByCAGkBaTOhKLzrYQdRF9Eloh6iPqIBo8B8ii4ZXeW/hsIqGV2OPlNOx8YpdpMUNk1hM7ga3wN5A+QtkLnrZCLEK0QLRBGiH6D0H4H8BIR+c0IP/vkFIhx++tkJyOjGPxHSuRt/gdz4C+TGXyA3/gK58RfIDbb9rSrvd190kD6eHbWjgDbZ4n8vnys22CvniiYtijL586nNRClXrXEdYbUPcKSwS2YUZXZmPUR9RIP0ZqiDo2FKlaMUNk5hkxQ2TWEzuETfA3kD5C2QueuknED26vOvKJqHARZoFSH6AUr/EchPQGgC6dGmCQQINUETCKycArwJBFZu/L0JBFZu/L0JBFZusFMmkD6q+Hb3YkNKcspo0qLNgJ4yHLpPsnXYiO4Ck+kBVpdo1UPURzRgRL+/Kt2LuhUfCqvEvXDQjHIm7gXZJCXvNIXN4Gp8D+QNkLdA5q6TcnbwBUvQAq0iRD9A6T8C+QkIzQ49sDQ7AOHw0+wAKzf+3uwAKzf+3uwAKzf+3uwAKzfYKbNDn8Z8++ywUXw5OzRpxT9GKzdobSYU8E82X/xZnQR10eoSUQ9R36Ek+jNAqyGiEaIxogmiKdY4g15/D+QNkLdA5q5oOQv4WslZAMj+BjD95G5i9QOU/iOQn4DQLNBDSrMAEA4zzQKw6iBy4yzE7MbZmwVQlhtnbxaAlRvnlFmQHCtVmvzOH02iQz+u9+I7kzZ9eNa4BU/mgLpodYmoh6jvkJQ5FD/EjCNEY0QTRFOsce6QlCc3QsoTUORl9G4N6XO87kQnn3GJK/DHBVEX0SWiHqK+Q2Jc0GqIaIRojGiCaIo1zh0S44JogSjykD8uyclITuPC37JJ9iGdKqAuoktEPUR9RANGdBi0j9shGiEaI5ogmiKau0bIceE+ivmCVpGH/HFJDhlyGhcbllb3f/qDyPSVmDiYJ6IU3RR2yUze/yHqIxqIwkQARb/9nlLlKIWNU9gkhU1T2Nw1Tg6i7b28b0OryEP+ICbR+1wGsVPlEHXS5jmiK0QLRJGH/G4kQeOcusEP+spuALqqAlogijzkdyOJTubUDRt+EnKZ04ck4t2CFBWgBVpFHvK7kYSRcuoGRCvm9Lsn0A2MaaBV5CG/G8nNfE7dgNvKeRXQFaIFoshDfjeSu66cugE3AXN6mRlGA+8e0CrykN+NnLfNnSpsFueIrhAtEEUe8rpRy3mX2Ykr8O6/5oiuEC0QRR7yu5HzpqxTg93JHNEVogWiyEN+N3Lew3TMFw/MvZjwG4iuEC0QRR7yu5G3F6d3nKEbgK7QaoEo8pDfjby9OH24BLqBXhytFogiD/ndSLx4NY8b/I55r1OLCr04Wi0QRR7yu5F48Zy6gV6cXjPUfgPRAlHkIb8biRfPqRvoxWvoxREtEEUe8ruRePGcuoFe3PxGs6+zK0QLRJGH/G4kXjynbqAXrwG6QrRAFHnI60Y98eL5dCOuwPcbiK4QLRBFHvK7kXjxnLqBXrwO6ArRAlHkIb8biRfPqRvoxeuArhAtEEUe8ruRePGcuoFevI5eHNECUeQhvxuJF8+pG+jF6+jFES0QRR7yu5G3F6+jF0d0hWiBKPKQ3428vXgdvTiiK0QLRJGHbDeOn96vVrv2crc8ex3/c7bd7FbXu/XmofC4fHr6tNnenBY77ZM2+SpjSi9Zmajq/Wr7btVa3d09Fa43Hx4I0x2ywIXt6va02K6GTRMtlBlsykV40jSfacEU+k5Zs0WfIkpJKZeabfts+b56WxoFEZsmpId5BpVK0zwLl5ZSpZT4xkGVRg9BNLv0IERanjrlic+cdAsoj3moBPOcV8pN81RsWkqFUtLadl6u0tVJq6dFKeYN27SrU6erk5bnvHxCKfERrGr1ebnRNK8wpbWNrrUNoKs8rXJApaWN3Hk5pFan9adFKS372CGURtcgPU9I9dB33NO0Q/XQk/Fp2qFrQN/mS8tDVzQ1hT4tS3pLHbkgbJrfZk25OkG5eZ56Dei3MpsX9hlO3VNKMT9LmNLqoEr1pClxWGkO0/h5gypJnTyNZjt16gQkAfoUTcqFCais1Ms8qzRnqZVTa1N5rdlOFWZIg08HsWnDRYOfPpAByc++UweXkWSR3nfqSYteuksZLlJF6sSgi5I6LUwVqdeqRtc9LQf91hsNbmodZo6nlNUJmpO0OqZBc5Y6uUiLaVLshM1JqkRp1Um75p1ycxLz42QJP3t9Qw5gsbxb09+08u/XdPNKrJ9U2H1+XJ0Wb1bX6/vlXbGweVxtl7sNPdD2brta7lbb+fvlw3Tb+dMHk7q8u9t8urhbPvxi3AY5kM2n/sPjh9149fS0fEflMOxst5uthCsD5uvdHdlM3n/5+/8+Fp6W68LNl9/+r3C3/vLbf3woFmKb02Lr/Zff/rPwYI3erf/xt8Ju++W3/yo8ffntv/+98P4f//PZJd59+fvf1v9SLDxuN/ePO790r2RrkF009eZPsY/r1qpVWt4G5q9KoVtrxu/W/rptfliT5/xLu92tter11it6t6XxqkJr3auTWqn7ql2vX3RJ/OXzWvuv5v2rzfb+w90yOKMHMPf/fn3sX/0zDZ7OXj/ShRwvt+/WNGx3q1vyxKUj80Hk7fqdef7H/sdu82j+afYxP292u829S3i/Wt6saPRKR7RTvd2Q7+f/oFlkSn672n14pJ0ADfPb9Z9pNOhmb7Ndrx52sVJOi4+b7W67XO+KhY+r7W59vbxrP66pPGpA01yAbf8mlvP63cNmu7qJR5paLf/TXckZX7sPD3eb619WN117SXjHkZZjWGvGb1HzBXuzfGBRfX0Rl5VS89I8z776uLyLW8f1HasWH9NW6Jd4C3T2/wAAAP//AwBQSwMEFAAGAAgAAAAhAE7SbdGfBgAAsB8AABMAAAB4bC90aGVtZS90aGVtZTEueG1s7FlLbxs3EL4X6H9Y7L2RZOsRG5ED6xXH8QuRkiJHSqJ2aXGXC5Kyo1uRnHopUCAteinQWw9F0QAN0KCX/hgDCdr0R3TIlXZJiYrtxCnSwhZg7HK/GQ5nhh9nZ2/dfhxR7wRzQVhc90s3ir6H4wEbkjio+w96nc9u+p6QKB4iymJc96dY+Le3Pv3kFtqUIY6wB/Kx2ER1P5Qy2SwUxACGkbjBEhzDsxHjEZJwy4PCkKNT0BvRwlqxWC1EiMS+F6MI1B6ORmSAvZ5S6W/Nlbcp3MZSqIEB5V2lGlsSGjsclxRCTEWTcu8E0boP8wzZaQ8/lr5HkZDwoO4X9Z9f2LpVQJszISpXyBpyHf03k5sJDMdrek4e9LNJy+VKubqd6dcAKpdx7Vq72q5m+jQADQaw0tQWW2dtrVmeYQ1QeunQ3aq11ksW3tC/vmTzdkX9LLwGpfrLS/hOpwletPAalOIrS/hKY6PRsvVrUIqvLuFrxe1WuWbp16CQkni8hC5WquvN+WozyIjRHSd8o1Lu1NZmynMUZEOWXWqKEYvlqlyL0DHjHQAoIEWSxJ6cJniEBpDFTURJnxNvjwQhJF6CYiZguLhW7BTX4b/6lfWVjijaxMiQVnaBJWJpSNnjiQEniaz7u6DVNyCvXr48e/Li7MlvZ0+fnj35ZTa3VmXJ7aA4MOXe/Pj1399/4f316w9vnn2TTr2IFyb+9c9fvv79j7ephxXnrnj17fPXL56/+u6rP3965tC+zVHfhPdIhIV3gE+9+yyCBTrsx31+OYleiIglgULQ7VDdlqEFPJgi6sI1sO3ChxxYxgW8Mzm2bO2GfCKJY+Z7YWQB9xmjDcadDrin5jI83JvEgXtyPjFx9xE6cc3dRLEV4PYkAXolLpXNEFtmHlEUSxTgGEtPPWNjjB2re0SI5dd9MuBMsJH0HhGvgYjTJT3StxIpF9ohEcRl6jIQQm35Zv+h12DUteoWPrGRsC0QdRjfw9Ry4x00kShyqeyhiJoO30MydBnZnfKBiWsLCZEOMGVee4iFcMkcclivEfR7wDDusO/TaWQjuSRjl849xJiJbLFxM0RR4rSZxKGJvSvGkKLIO2LSBd9n9g5R9xAHFK8M90OCrXCfTwQPgFxNk/IEUU8m3BHLO5jZ+3FKRwi7WGabRxa7bnPizI7GJLBSew9jik7REGPvwV2HBQ2WWD7Pjd4NgVV2sCuxdpGdq+o+xgLKJFXXLFPkHhFWynZxwFbYsz9dIJ4piiPEV2k+gKhbqQunnJNKD+lgbAIPCJR/kC9OpxwK0GEkd3uV1qMQWWeXuhfufJ1yK34X2WOwL48vuy9BBl9aBoj9wr7pIWpNkCdMD0GB4aJbELHCn4uoc1WLTZxyI3vT5mGAwsiqdyISn1v8LJQ9lX+n7HEXMFdQ8LgVv0+ps4pSdhYKnFW4/2BZ00KT+AjDSbLMWddVzXVV4//vq5pVe/m6lrmuZa5rGdfb1wepZfLyBSqbvMujez7RypbPiFDalVOK94Tu+gh4oxl2YFC3o3RPMmsBJiFczhpMFi7gSMt4nMnPiQy7IUqgNVTSDcxAzFQHwkuYgI6RHtatVLygW/edJtE+G6adzlJJdTVTFwok8/FiJRuHLpVM0dVa3r3L1Ot+aKC7rHMDlOxljDAms41YdxhRmw9CFN5mhF7ZlVix4bDiplI/D9U8ipkrwLQsKvDK7cGLet2vlNMOMjTjoDwfqjilzeR5dFVwrjTSq5xJzQyAEnueAXmkN5StK5enVpem2gUibRlhpJtthJGGIbwIz7LTbLlfZaw38pBa5ilXzHdDbkbt5oeItSKRBW6gsckUNPZO6351vQJfVQYoqfsj6BjDZZRA7gj11oVoAJ9dBpKnG/5dmCXhQraQCFOHa9JJ2SAiEnOPkqjuq+Vn2UBjzSHattIaEMJHa9wG0MrHZhwE3Q4yHo3wQJphN0aUp9NbYPiUK5xPtfi7g5Ukm0C4u+Hw1OvTCb+PIMUqtZJy4JAI+HBQSr05JPAlLCOyPP8WDqYZ7ZqfonQOpeOIJiGanSgmmadwTaKZOfou84FxN1szOHTZhf1AHbDvfeqef1QrzxmkmZ+ZFquoU9NNph/ukDesyg9Ry6qUuvU7tci5bmPOdZCozlPinFP3AgeCYVo+mWWasniZhhVnz0Zt066wIDA8UV3ht+yMcHriXU9+kFvMWnVAzOtKnfj6k7n5VZv1j4E8WvD9cEKl0KGE3i5HUPSlXyAz2tCiW/8AAAD//wMAUEsDBBQABgAIAAAAIQB85K9BcAkAAIyMAAANAAAAeGwvc3R5bGVzLnhtbOxdX2/iRhB/r9TvYDlSH6oS/+FPgELSS3JIJ11Pp0sq9eGkyJgFtmd7qb3kyFV96dfpt+on6axtwAYMZvF/koeAzXp3fju7M7Mzs+vezcI0hGdkO5hYfVG5lEUBWToZYWvSF397HNTaouBQzRppBrFQX3xBjnhz/f13PYe+GOhhihAVoArL6YtTSmddSXL0KTI155LMkAW/jIltahQu7YnkzGykjRz2kGlIqiy3JFPDlujV0DX1OJWYmv1lPqvpxJxpFA+xgemLW5comHr33cQitjY0gNSF0tB0YaG0bFVY2MtG3Ltb7ZhYt4lDxvQS6pXIeIx1tE1uR+pImr6uCWrmq0lpSrIawr6wOWtqSDZ6xox94nXPmpsDkzqCTuYW7Yvq6pbg/fJuBDxuNUTB48odGUE/PdV+FC5+uriQL2X5s/DDn3NCf/7vn3+9L0+1nz8f+J097xWueR83N7uqear98lQTpSWRIYquwhQxai5YUckHdN0bE2uNS2kBDxh3u18s8tUasN8AGKBlxa57zjfhWTPgjsoq0YlBbIHCqASwikuBZiKvxCM2kSN8QF+FT8TULPbjWDOx8eL97D4veZV6/4dQYlW9vK4eWyO0QNC97XADb2ysGTur1aea7cDs8Sht1V28m03hsjYX6rTkUISqXfLB7XKPy8ezIZK7J9V6kLnBLkm3pdCIDUyIqK46MCXcCXQSd49u4Jj5dhr1aXRPaJRaK8kTLRh2jnElhqy50ww8tLHwHk+mdFPmuHzbNSxdfe2LQ1P7g9hbgmhX/6csTu3JsC8O4E+Gv7BE9VHGlqkhfBisgwA+t6sdkPnYMFZas870CNy47oGBQZFtDeBC8L8/vsxAi1hgC3nVuOUOlJ7Y2ouiNuM/4BADjxgVk7ug7mqKAsVMr8uXV51Op6202u12p1FXGg134A794quZDZqeKdEADLjyiHU/APmQ2COw/pYWQ50pUe/edc9AYwrP22w4wSclM/g/JJSCiXTdG2FtQizNYC0snwg+CWYjWIh9kU7Bwltq4bDQkVgLfgNxiruUuITEKQ30LsldFp9q2I6ixQNWEFz7CD0jXPvGTqH4tY/QHfzKAZc3gcszb8L0Vm0+rARpHIakNNJPGhFJjOCwbuEcmlUVESPQs4gZAbsWNqBwmRY+VVn59sEOLRzVuv9EXEXsF98hAQ80UDh8B+g9S4S7p57P82M5eKCDKzBGM0CY+ygtJMacx+ne5gsnSY/n4JH4SjhGU0eYyAhdmlP7DamiafATqc5tNGVOd4ZjxHVIS9uiqfirsJNWjUmuafjcWUd2cP4E5+D3iPBIJrmQjje3N2dJKmt6PlKq6h495H/2HdHg19aRYTwwB/Tv45Vzm/m2F+NA4BmSHVjAlUXF2Vfw5ftfPT+2d8H828HavLqD1SpXXBULi/GqhSiywOW/kywFAuD+04I2mxkvLAbOotv+FUBZX926Pv719RsDTywTBR/4aBOKdOolgQAaiCR5RYQpsfE3qJzF03V4BkEmBeSLUKwH7kAfzVY1CAbRv7BQuBu4kRbj6F6PgqdWG1692vAgv6QKgzNaJGzAO2o+nTZ3YIIfllgb5H2Ym0NkD9w8LE4hkNiEj92nmwKJS7zAPIsQ6kcM0Ay5G0sfbZIeEvX5EMsSynYrz2L2c2AWRWmgLRm2exaVSO36eX+HzJ2iCY8YvNoyhsrPq7WYj20inQPoLcOpWrMytrWfI2wWiNmxAhC+2trsES3cRchRy4GQXCrDaM+nB6BnwkZ1xmNgywRMmeMsxTu0ws0bL/+gBig7zSPIes8VYvJL+yRtDJZ1mctyJZZAAlP9VN5xu2Fcx/ypXpgQytgG/PGTMGdnUyxmwh6nwkzECO2SvErtVA30YZs5b8gn+n68jVuJLOBOEK5BrZG8JGLLvViuhAwl0XmgTMa5X3jlmbh8je3SjBix/GZOyvYb25RZhKmYoNSMWl5mbc0l5k9XOF3cpQxZJBITAFuPx1edj2MdDJbyEAtbFMtEbRYzJ9XgeTrxycTNO56gFveiMQntHiA4oC8gJWGdFcKGesFC3HHzLMI4qgGjeOkiXNwoXloIF4zipX+UCMaeteY2Chj3y2yQKElVpDj2UdiUlnsojOftgINcIvLguGK/6SfECc7UxtaXRzLAPBGxWNC3pF4cl0g1oHPFgasBnWtCVwM6Vwi0GtC5oqHVgM4VJa0GdK64VDWgc4VqKgFd5XJGVgP6+VpzahWtuYAnJXZcb19Gba5uoViRrSKlokblqVHI0vtEKByeyo587bi7dOKn11cmXS+DbihSumqOo6EU+dlnlMAaGelPuQ+K5IvKJ4m3BD3Au5UzXwWf+M5UJfs9TWlG3qL8p0fFsYqzbzj7jX2pRnKj5o665fvIZL9ZwkFUJXJTRz7w0tzFHoquFiwQtqndKxvci7dEqZoujoc6721EQTmaWap73nuJYoBOe/lRhqVoylsIX5cfcAZ94Te6JDQRovbc1RNI9c3A156gc6rUuw+FDLx0RZoUeblm1CLtBsurE4pkJuQ2EEpxxELa1lIpTn9JuxNe5WJfPB+DKdJJU4J9winbjOWYCBmYjCWxEjLoiXKYClkMiXLYC1n0RDmMhix64uwEZpTyfD1YhJ1NXLzTypI/TaUEnE55vfBqJ5Yjz2lLAaRsPXMltobPp8nD4Zq2H7oMZ79te19T7pUiSdG0PXBRfvlz8sRG9YF6Tq7YyE6o+PmQkbhLIQV48ySzOH8mp4M947oC9r6chP+Qn1gJMCVIBUnh9OQSZH9w5x1zJh6fmszKS28WRzolMv/dlx7Ba44C71IKvUlp9U4kwdJM1Bc/sBeMGAGzdjjHBsXWjrcoQZ2jxfq9TO4OJKoNDeS+sWnVCqRqjNBYmxv0cfVjX1x//xWN8NyE9YVf6iN+JtStoi+uv7/HkylVWiIwDDY+vXeo+ynMbdwX/3p7e9W5fztQa235tl1r1FGz1mne3teajbvb+/tBR1blu78Bk2lYTnehNPrilNJZV5IcfYpMzbk0sW4Th4zppU5MiYzHWEeSM7ORNnKmCFHTkFRZ7kgdydSwxd4TpTS6jgGlbB+sT/zD+l5fDFx45DPqJSA/SHtHbclvmopcG9RlpdZoae1au1Vv1gZNRb1vNW7fNgfNAO1NPtoVWVKUNfHNLsUmMrC15NWSQ8G7wCS43AOCQXE5ITnsHV0PrKeu/wcAAP//AwBQSwMEFAAGAAgAAAAhAKu9RiImAwAAOwcAABQAAAB4bC9zaGFyZWRTdHJpbmdzLnhtbIxVwW7TQBC9V8o/jHwqEsFxKFWJkiDqliRKMQE2iKtxTGyRbEK8ruixRAi1gCgChBAgCoUeChWVevNKcNgo/7F/wjgppbK3iFwc75t5M/N2Zly89KDbgVV3EPg9WtKMczkNXOr0Wj5tl7QmuZJd0CBgNm3ZnR51S9qaG2iXypmZYhAwQF8alDSPsX5B1wPHc7t2cK7Xdykid3uDrs3wddDWg/7AtVuB57qs29Hzudy83rV9qoHTCykraQsYNqT+/dA1pwdzC1q5GPjlIiuTquRbVgXqYhPIDRlFsHwV5mG0JaOfFhhzQJqSv6pBA+1egSmj7w2o1MT6NViS/IsJpCb5wyYg+tQs6qxc1GPeKfdVGX0LC0Cq2ZyRJctJ2BoNuxD41EsCRPLXtJ2ZmZ3PGrkzp6KGkTXmUjBmzt8CC5HDV7tCIPmLVDKS/0ieLYnPFBjSOUmk7oVrMvrFMjNMRvssCZviEO55MtoBOhrSNlRJ0mK0NT6QfMcB5iNPHxykoVBZStrdxFShH1P58YO/nlj2YbbRMBWlix1YFdswemFjVDR/NgnAh+H0Jcm+Ivm7PhiqoJkZjJDWL/rkg4PEb1L6jRG554lPKa2sYwTzwmKpOou8+vi8+nhOfXwheVwlJiFVpap1RYEr44MQ7tipFCfXkLaPR7QQ9G0HRxdnMHAHq65WXpT8+ZH4ysDIgxqOD2zUw1dfDPHFXohGYl/J0Jk0D22n74dvQEfyxylgICOOYz0di7hHerGd6vILal/D+OOslpRMIvy1OtmCkn/EJaDmnbZEvGiOcvsXfZ2AkxotVPH/Zolg337wY9ElH3YLQNtiew3O54Bh2+K8XIyntQv5XD7VRriRNqhXAKuNHI/hcqpBrMr4h+Tva7Ay2ZCLMvpsVZIV3xbrJlhVtLBwk/Ldy9BctJbgthjqjerEP+3TqIqXYOJ63QVMYtNMyThbF/vAxB49i5WJQ6yjJaOvYWo5NLDjsH7EiSe2qQe3VJv3L3T2SB+If0cKTf6fKpLVxqXIH1G4HsbrR8V/bBLfxROwMCe0lvzw5EdAx49f+TcAAAD//wMAUEsDBBQABgAIAAAAIQA7bTJLwQAAAEIBAAAjAAAAeGwvd29ya3NoZWV0cy9fcmVscy9zaGVldDEueG1sLnJlbHOEj8GKwjAURfcD/kN4e5PWhQxDUzciuFXnA2L62gbbl5D3FP17sxxlwOXlcM/lNpv7PKkbZg6RLNS6AoXkYxdosPB72i2/QbE46twUCS08kGHTLr6aA05OSonHkFgVC7GFUST9GMN+xNmxjgmpkD7m2UmJeTDJ+Ysb0Kyqam3yXwe0L0617yzkfVeDOj1SWf7sjn0fPG6jv85I8s+ESTmQYD6iSDnIRe3ygGJB63f2nmt9DgSmbczL8/YJAAD//wMAUEsDBBQABgAIAAAAIQDMatf1kwIAAAQLAAAnAAAAeGwvcHJpbnRlclNldHRpbmdzL3ByaW50ZXJTZXR0aW5nczEuYmlu7FXNahRBEP6qune6ZzfZnU2ixr+4iX+JB4m6gt42ThQDEgU9BBEhMFECkoDG+yJ4F495Fg/ixZfwEXwBQVi/nhlNjCJjkouSanq3q6u/+uuqnhTLWMM6Zwd3cAP3cBnXMctRjcROmE+YrpuPAkGMzUbXZ1xZLGnYAadgDt2K+v7mWNCuuYXifyc2XV5bX+PmV19KCMgxERDbdwbvY58i3WMGCtsDB3yWL8GbTIyKMVZrGmUiXLdsUovgtjPexFKXhg7psDa1ZVAPUjWaw9Sp1zgoCjsShEo9YqVWp06nzjge9B3aa/wCxNDwcI4tdQma31VpTSLbd7bnbQ+tsOs7xnfsTzppo+kESQEKRiUSJ96PxIo2zWEkE9oeDV7ZKaxkknnDkOm803grKs39ZghITNuM6KiO6SE9rEcCMGyP61E5JsflhJzUCT2lHZ3UKT2tZ/SsnNPzOq0zesFBS/eZ0CIzWtc8ddJUa6daCptZU4uCNC5lLU20rahtRb4FjsaIjkLiwWz6SfVt3o43YMpzx6jMT0Ymv4VcX3EDanxifQJvGjoYsPR619AJFWU5Y44uK22zAVwhPxNqgfxj8pde/1kq2me/LClExoO+bHspt9iSzHnRTbzvUvYmHJzDc6yygJ/trP2KvAsNERRVInb0o3Tx4ezs1YsLaVrd5G5x9Ow39lRIyuwHv2POwWCX0f9/sLcMKcVdLOIWFjCPm1w94GqOj3tV2iv+9n4WaL/f/+H3h6JQHcKwnFWIdTKPFTxhk7xkm2zwO3ef/AbHKr96T/FiX6sgdKeBRggPNrs6kDQMG5h84bmDKYkNz3V+hD/skpJ2UdAFlo+XDZ1RlV7xbU32Nf4DZQcZ+Ncy8A0AAP//AwBQSwMEFAAGAAgAAAAhACRNxph0AQAA6AUAABAAAAB4bC9jYWxjQ2hhaW4ueG1sZJTNboMwEITvlfoOlu+NY5umPwrJoRIc9uJD+wAWuAEJTIRR1b59raqhzc6RwVrP7HywP36Og/gIc+qnWEq92UoRYjO1fTyV8u21unuUIi0+tn6YYijlV0jyeLi92Td+aF4630eRJ8RUym5Zzs9KpaYLo0+b6RxifvM+zaNf8uN8Uuk8B9+mLoRlHJTZbndqzAPkYd+IuZROGyn6UlophmxFqlW//9X/lB1XTAHKAyg5y8/8dY7lc0jn26/OkIYzhvshwyeThdtBADdPEDO3cW1Ya6ZUxWVpl1A1KA5COQ3r0uBPg0ENDg04NNyhM9yhM3zJDlbqDF97VfDJNSjOcIdVwe+qQXEWUlhIYSGFhRQWtmoBXQTDwp6BON4NAW88N2meiYAdWj+4CzsEXJAG2IEUAlIISCEghYAUAlIISCH40AlIIQP7Ai4IOifonKBzgs4JOifonPA3A50T4s4LrAuuVAUHrv6vqPUfffgGAAD//wMAUEsDBBQABgAIAAAAIQCXFxc1ewEAAJwCAAARAAgBZG9jUHJvcHMvY29yZS54bWwgogQBKKAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAB8kt1KwzAcxe8F36HkvkuyrnOGrsMPRMGJYEXxLiT/bcUmLUnm3FsIPocvoLe+iG9i1m51fuBle875cc6fJKNHVQQPYGxe6iGiHYIC0KKUuZ4O0XV2Eg5QYB3XkhelhiFagkWjdHcnERUTpYFLU1ZgXA428CRtmaiGaOZcxTC2YgaK2453aC9OSqO4859miisu7vkUcJeQPlbguOSO4xUwrFoiWiOlaJHV3BQ1QAoMBSjQzmLaofjL68Ao+2egVracKnfLym9a191mS9GIrfvR5q1xsVh0FlFdw/en+HZ8flVPDXO9upUAlCZSMGGAu9KkB8fjs4sEb/1ZXa/g1o39oSc5yMNlesFV8P708foyD04/3p71NMG/TZvcpcm1A5l2STcOaTekJKM9Fu2zKL5rcxuTr1Ivb/qADPwW1izfKDfR0XF2ghoe2Q/JXkZjFu8xEnnej/xqWwNU6/r/E/shGYSUZmTAejGjgy3iBpDWpb+/p/QTAAD//wMAUEsDBBQABgAIAAAAIQDf3d+9kgEAABQDAAAQAAgBZG9jUHJvcHMvYXBwLnhtbCCiBAEooAABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAJySwWrcMBCG74W8g9E9K29aQllkhbJpyKGlC+ukZ0Uer0VkyWgmZrdPU+ij5MU6tsnG2+TU28z8P78+jaSu9q3PekjoYijEcpGLDIKNlQu7QtyVN+efRYZkQmV8DFCIA6C40mcf1CbFDhI5wIwjAhaiIepWUqJtoDW4YDmwUsfUGuI27WSsa2fhOtqnFgLJizy/lLAnCBVU590xUEyJq57+N7SKduDD+/LQMbBWX7rOO2uIb6m/O5sixpqyr3sLXsm5qJhuC/YpOTroXMl5q7bWeFhzsK6NR1DydaBuwQxL2xiXUKueVj1YiilD94vXdiGyB4Mw4BSiN8mZQIw12KZmrH2HlPTPmB6xASBUkg3TcCzn3nntPunlaODi1DgETCAsnCKWjjzgj3pjEr1DvJwTjwwT74RTxuffIds//3mDON6aD/snfh3bzoQDC8fqmwuPeNeV8doQvGz0dKi2jUlQ8SMcN34cqFteZvJDyLoxYQfVi+etMLz//fTJ9fJykX/M+WlnMyVfv7P+CwAA//8DAFBLAQItABQABgAIAAAAIQB0NlqmegEAAIQFAAATAAAAAAAAAAAAAAAAAAAAAABbQ29udGVudF9UeXBlc10ueG1sUEsBAi0AFAAGAAgAAAAhALVVMCP0AAAATAIAAAsAAAAAAAAAAAAAAAAAswMAAF9yZWxzLy5yZWxzUEsBAi0AFAAGAAgAAAAhAFd1o5RGAwAAxgcAAA8AAAAAAAAAAAAAAAAA2AYAAHhsL3dvcmtib29rLnhtbFBLAQItABQABgAIAAAAIQCSB5TsBAEAAD8DAAAaAAAAAAAAAAAAAAAAAEsKAAB4bC9fcmVscy93b3JrYm9vay54bWwucmVsc1BLAQItABQABgAIAAAAIQCnyTlGRh0AAKKfAAAYAAAAAAAAAAAAAAAAAI8MAAB4bC93b3Jrc2hlZXRzL3NoZWV0MS54bWxQSwECLQAUAAYACAAAACEATtJt0Z8GAACwHwAAEwAAAAAAAAAAAAAAAAALKgAAeGwvdGhlbWUvdGhlbWUxLnhtbFBLAQItABQABgAIAAAAIQB85K9BcAkAAIyMAAANAAAAAAAAAAAAAAAAANswAAB4bC9zdHlsZXMueG1sUEsBAi0AFAAGAAgAAAAhAKu9RiImAwAAOwcAABQAAAAAAAAAAAAAAAAAdjoAAHhsL3NoYXJlZFN0cmluZ3MueG1sUEsBAi0AFAAGAAgAAAAhADttMkvBAAAAQgEAACMAAAAAAAAAAAAAAAAAzj0AAHhsL3dvcmtzaGVldHMvX3JlbHMvc2hlZXQxLnhtbC5yZWxzUEsBAi0AFAAGAAgAAAAhAMxq1/WTAgAABAsAACcAAAAAAAAAAAAAAAAA0D4AAHhsL3ByaW50ZXJTZXR0aW5ncy9wcmludGVyU2V0dGluZ3MxLmJpblBLAQItABQABgAIAAAAIQAkTcaYdAEAAOgFAAAQAAAAAAAAAAAAAAAAAKhBAAB4bC9jYWxjQ2hhaW4ueG1sUEsBAi0AFAAGAAgAAAAhAJcXFzV7AQAAnAIAABEAAAAAAAAAAAAAAAAASkMAAGRvY1Byb3BzL2NvcmUueG1sUEsBAi0AFAAGAAgAAAAhAN/d372SAQAAFAMAABAAAAAAAAAAAAAAAAAA/EUAAGRvY1Byb3BzL2FwcC54bWxQSwUGAAAAAA0ADQBkAwAAxEgAAAAA"

HELPER_BLOCK = r'''
# === BAI_13C_1_TH_M1_START ===
TH_M1_TEMPLATE_PATH = (
    APP_DIR
    / "report_templates"
    / "pcgd_xmc_2025"
    / "PCGD_2025_TH_M1.xlsx"
)

_TH_M1_AGE_COLUMNS = {
    6: 6,
    7: 7,
    8: 8,
    9: 9,
    10: 10,
    11: 12,
    12: 13,
    13: 14,
    14: 15,
}

_TH_M1_TOTAL_COLUMNS = {
    "6_10": 11,
    "11_14": 16,
}


def _th_m1_norm(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.split())


def _th_m1_reference_year(school_year: SchoolYear | None) -> int:
    if school_year is not None:
        match = re.search(r"(20\d{2})", str(school_year.code or ""))
        if match:
            return int(match.group(1))
    return datetime.now().year


def _th_m1_is_female(person: SurveyPerson) -> bool:
    return _th_m1_norm(person.gender) in {"NU", "F", "FEMALE", "GIRL"}


def _th_m1_is_ethnic_minority(person: SurveyPerson) -> bool:
    ethnic = _th_m1_norm(person.ethnic_group)
    return bool(ethnic) and ethnic not in {"KINH", "K"}


def _th_m1_grade(record: SurveyPersonYearRecord | None) -> int | None:
    if record is None:
        return None
    class_name = ""
    if record.classroom is not None:
        class_name = str(record.classroom.name or "")
    if not class_name:
        class_name = str(record.class_name_reported or "")
    normalized = _th_m1_norm(class_name)
    if not normalized:
        return None
    match = re.search(r"(?<!\d)(1[0-2]|[1-9])(?=[A-Z]|\b|\s|/|\-|$)", normalized)
    if not match:
        return None
    grade = int(match.group(1))
    return grade if 1 <= grade <= 12 else None


def _th_m1_completed_primary(
    person: SurveyPerson,
    record: SurveyPersonYearRecord | None,
) -> bool:
    if record is None:
        return False
    status = _th_m1_norm(record.learning_status)
    if status in {"DA TOT NGHIEP", "DA_TOT_NGHIEP", "HOAN THANH", "HTCTTH"}:
        return True
    grade = _th_m1_grade(record)
    if grade is not None and grade >= 6:
        return True
    combined_notes = _th_m1_norm(
        " ".join(
            [
                str(record.notes or ""),
                str(person.notes or ""),
                str(person.special_circumstances or ""),
            ]
        )
    )
    return (
        "HOAN THANH CHUONG TRINH TIEU HOC" in combined_notes
        or "HTCTTH" in combined_notes
    )


def _th_m1_is_disabled(
    person: SurveyPerson,
    record: SurveyPersonYearRecord | None,
) -> bool:
    if record is not None and str(record.disability_status or "").upper() == "CO_KHUYET_TAT":
        return True
    if person.student is not None and str(person.student.disability_type or "").strip():
        return True
    return False


def _th_m1_disability_accessed_education(
    person: SurveyPerson,
    record: SurveyPersonYearRecord | None,
) -> bool:
    if not _th_m1_is_disabled(person, record) or record is None:
        return False
    status = str(record.learning_status or "").upper()
    return status in {
        "DANG_HOC",
        "CHUYEN_DEN",
        "CHUYEN_DI",
        "DA_TOT_NGHIEP",
    }


def _th_m1_is_ppc(
    person: SurveyPerson,
    record: SurveyPersonYearRecord | None,
) -> bool:
    # Quy tắc an toàn giai đoạn đầu: chỉ đối tượng thường trú được tính
    # vào số phải phổ cập. Không suy diễn thêm các trường dữ liệu chưa có.
    if str(person.residency_status or "").upper() != "THUONG_TRU":
        return False
    if record is not None and str(record.learning_status or "").upper() == "KHONG_THUOC_DIEN":
        return False
    return True


def _th_m1_school_commune_id(
    record: SurveyPersonYearRecord | None,
) -> int | None:
    if record is None or record.school is None:
        return None
    return int(record.school.commune_id) if record.school.commune_id is not None else None


def _th_m1_location_bucket(
    person: SurveyPerson,
    record: SurveyPersonYearRecord | None,
    reporting_commune_id: int | None,
) -> str:
    home_commune_id = (
        int(person.household.commune_id)
        if person.household is not None and person.household.commune_id is not None
        else None
    )
    school_commune_id = _th_m1_school_commune_id(record)

    if reporting_commune_id is None:
        # Ở phạm vi toàn tỉnh, trường có mã trong danh mục tỉnh được xem là
        # tại chỗ; tên trường chỉ ghi tay/không có mã được xem là nơi khác.
        if record is not None and record.school_id is None and str(record.school_name_reported or "").strip():
            return "other"
        return "local"

    if home_commune_id == reporting_commune_id:
        if school_commune_id is None:
            if record is not None and str(record.school_name_reported or "").strip():
                return "other"
            return "local"
        return "local" if school_commune_id == reporting_commune_id else "other"

    if school_commune_id == reporting_commune_id:
        return "inbound"
    return "other"


def _th_m1_empty_age_metric() -> dict[str, Any]:
    return {
        "total": 0,
        "female": 0,
        "ethnic": 0,
        "disabled": 0,
        "disabled_access": 0,
        "ppc": 0,
        "grades": {
            grade: {"local": 0, "other": 0, "inbound": 0}
            for grade in range(1, 6)
        },
        "completed": {"local": 0, "other": 0, "inbound": 0},
        "nonppc_completed": 0,
        "dropout": {"local": 0, "other": 0, "inbound": 0},
        "not_started": 0,
    }


def _th_m1_load_people_and_records(
    *,
    db: Session,
    request: Request,
    school_year_id: int,
    selected_commune_id: int | None,
    selected_school_id: int | None,
) -> list[tuple[SurveyPerson, SurveyPersonYearRecord | None]]:
    form_filters = list(_form_scope_filters(request, selected_school_id))
    statement = (
        select(SurveyForm)
        .where(
            SurveyForm.survey_batch.has(
                SurveyBatch.school_year_id == school_year_id
            ),
            *form_filters,
        )
        .options(
            selectinload(SurveyForm.household)
            .selectinload(Household.people)
            .selectinload(SurveyPerson.student)
        )
    )
    if selected_commune_id is not None:
        statement = statement.where(
            SurveyForm.household.has(
                Household.commune_id == selected_commune_id
            )
        )

    forms = list(db.scalars(statement).unique().all())
    person_map: dict[int, SurveyPerson] = {}
    form_ids: list[int] = []
    for form in forms:
        form_ids.append(int(form.id))
        if form.household is None:
            continue
        for person in form.household.people:
            if bool(person.is_active):
                person_map.setdefault(int(person.id), person)

    if not person_map:
        return []

    record_statement = (
        select(SurveyPersonYearRecord)
        .where(
            SurveyPersonYearRecord.school_year_id == school_year_id,
            SurveyPersonYearRecord.survey_person_id.in_(list(person_map)),
            SurveyPersonYearRecord.survey_form_id.in_(form_ids),
        )
        .options(
            selectinload(SurveyPersonYearRecord.school),
            selectinload(SurveyPersonYearRecord.classroom),
        )
        .order_by(
            SurveyPersonYearRecord.is_reviewed.desc(),
            SurveyPersonYearRecord.updated_at.desc(),
            SurveyPersonYearRecord.id.desc(),
        )
    )
    records = list(db.scalars(record_statement).all())
    latest_record: dict[int, SurveyPersonYearRecord] = {}
    for record in records:
        latest_record.setdefault(int(record.survey_person_id), record)

    return [
        (person, latest_record.get(person_id))
        for person_id, person in person_map.items()
    ]


def _th_m1_build_metrics(
    *,
    people_and_records: list[tuple[SurveyPerson, SurveyPersonYearRecord | None]],
    reference_year: int,
    reporting_commune_id: int | None,
) -> dict[int, dict[str, Any]]:
    metrics = {age: _th_m1_empty_age_metric() for age in range(6, 15)}

    for person, record in people_and_records:
        if person.date_of_birth is None:
            continue
        age = reference_year - int(person.date_of_birth.year)
        if age not in metrics:
            continue

        item = metrics[age]
        item["total"] += 1
        if _th_m1_is_female(person):
            item["female"] += 1
        if _th_m1_is_ethnic_minority(person):
            item["ethnic"] += 1

        if _th_m1_is_disabled(person, record):
            item["disabled"] += 1
            if _th_m1_disability_accessed_education(person, record):
                item["disabled_access"] += 1

        ppc = _th_m1_is_ppc(person, record)
        if ppc:
            item["ppc"] += 1

        bucket = _th_m1_location_bucket(person, record, reporting_commune_id)
        grade = _th_m1_grade(record)
        learning_status = str(record.learning_status or "").upper() if record is not None else ""

        if ppc and grade in {1, 2, 3, 4, 5} and learning_status not in {
            "BO_HOC",
            "THOI_HOC",
            "CHUA_DI_HOC",
            "TAM_NGHI",
        }:
            item["grades"][grade][bucket] += 1

        completed = _th_m1_completed_primary(person, record)
        if completed:
            if ppc:
                item["completed"][bucket] += 1
            else:
                item["nonppc_completed"] += 1

        if ppc and learning_status in {"BO_HOC", "THOI_HOC"}:
            item["dropout"][bucket] += 1

        if ppc and learning_status == "CHUA_DI_HOC":
            item["not_started"] += 1

    return metrics


def _th_m1_scope_title(
    scope_label: str,
    selected_commune_id: int | None,
) -> str:
    text = str(scope_label or "").strip()
    if selected_commune_id is not None:
        return text
    if text.lower().startswith("trường "):
        return text
    return "Toàn tỉnh" if text == "Toàn tỉnh" else text


def _th_m1_write_age_row(
    ws: Any,
    row_number: int,
    metrics: dict[int, dict[str, Any]],
    value_getter: Any,
    *,
    blank_zero: bool = True,
) -> None:
    values_6_10: list[int] = []
    values_11_14: list[int] = []
    for age, column in _TH_M1_AGE_COLUMNS.items():
        value = int(value_getter(metrics[age]) or 0)
        ws.cell(row_number, column).value = None if blank_zero and value == 0 else value
        if age <= 10:
            values_6_10.append(value)
        else:
            values_11_14.append(value)
    ws.cell(row_number, _TH_M1_TOTAL_COLUMNS["6_10"]).value = sum(values_6_10)
    ws.cell(row_number, _TH_M1_TOTAL_COLUMNS["11_14"]).value = sum(values_11_14)


def _th_m1_percent(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round((numerator * 100.0) / denominator, 2)


def _build_primary_th_m1_workbook(
    *,
    db: Session,
    request: Request,
    school_year: SchoolYear | None,
    selected_commune_id: int | None,
    selected_school_id: int | None,
    scope_label: str,
) -> tuple[Any, str]:
    if school_year is None:
        raise ValueError("Chưa xác định được năm học để lập biểu TH-M1.")
    if not TH_M1_TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Không tìm thấy mẫu TH-M1: {TH_M1_TEMPLATE_PATH}")

    reference_year = _th_m1_reference_year(school_year)
    people_and_records = _th_m1_load_people_and_records(
        db=db,
        request=request,
        school_year_id=int(school_year.id),
        selected_commune_id=selected_commune_id,
        selected_school_id=selected_school_id,
    )
    metrics = _th_m1_build_metrics(
        people_and_records=people_and_records,
        reference_year=reference_year,
        reporting_commune_id=selected_commune_id,
    )

    workbook = load_workbook(TH_M1_TEMPLATE_PATH)
    ws = workbook[workbook.sheetnames[0]]

    # Chỉ thay nội dung dữ liệu; giữ nguyên tên sheet, merge, font, border,
    # kích thước dòng/cột, vùng in và bố cục mẫu gốc.
    scope_title = _th_m1_scope_title(scope_label, selected_commune_id)
    ws["A1"] = "Tỉnh: Nghệ An"
    ws["A2"] = scope_title
    ws["E2"] = f"Thời điểm: ngày 30 tháng 9 năm {reference_year}"
    ws["J44"] = f"{scope_title}, ngày      tháng      năm {reference_year}"

    birth_years = {
        6: reference_year - 6,
        7: reference_year - 7,
        8: reference_year - 8,
        9: reference_year - 9,
        10: reference_year - 10,
        11: reference_year - 11,
        12: reference_year - 12,
        13: reference_year - 13,
        14: reference_year - 14,
    }
    for age, column in _TH_M1_AGE_COLUMNS.items():
        ws.cell(4, column).value = birth_years[age]

    # Xóa toàn bộ số liệu ví dụ của địa phương mẫu trước khi điền dữ liệu thật.
    for row_number in range(6, 39):
        for column in range(6, 17):
            ws.cell(row_number, column).value = None
    for row_number in range(40, 45):
        ws.cell(row_number, 6).value = None
        ws.cell(row_number, 7).value = None

    _th_m1_write_age_row(ws, 6, metrics, lambda item: item["total"])
    _th_m1_write_age_row(ws, 7, metrics, lambda item: item["female"])
    _th_m1_write_age_row(ws, 8, metrics, lambda item: item["ethnic"])
    _th_m1_write_age_row(ws, 9, metrics, lambda item: item["disabled"])

    # Dòng 10 "Có khả năng HT": hệ thống hiện chưa có trường dữ liệu trực tiếp.
    # Cố ý để trống, không suy diễn và không sửa cơ sở dữ liệu.
    _th_m1_write_age_row(ws, 11, metrics, lambda item: item["disabled_access"])
    _th_m1_write_age_row(ws, 12, metrics, lambda item: item["ppc"])

    grade_row_starts = {1: 13, 2: 16, 3: 19, 4: 22, 5: 25}
    bucket_offsets = {"local": 0, "other": 1, "inbound": 2}
    for grade, start_row in grade_row_starts.items():
        for bucket, offset in bucket_offsets.items():
            _th_m1_write_age_row(
                ws,
                start_row + offset,
                metrics,
                lambda item, grade=grade, bucket=bucket: item["grades"][grade][bucket],
            )

    for bucket, offset in bucket_offsets.items():
        _th_m1_write_age_row(
            ws,
            28 + offset,
            metrics,
            lambda item, bucket=bucket: item["completed"][bucket],
        )
    _th_m1_write_age_row(ws, 31, metrics, lambda item: item["nonppc_completed"])

    # Dòng 32-34 "Lưu ban": chưa có trường dữ liệu trực tiếp nên để trống.
    for bucket, offset in bucket_offsets.items():
        _th_m1_write_age_row(
            ws,
            35 + offset,
            metrics,
            lambda item, bucket=bucket: item["dropout"][bucket],
        )
    _th_m1_write_age_row(ws, 38, metrics, lambda item: item["not_started"])

    age6 = metrics[6]
    age11 = metrics[11]
    primary_age11 = sum(
        age11["grades"][grade][bucket]
        for grade in range(1, 6)
        for bucket in ("local", "other")
    )
    grade1_age6 = sum(age6["grades"][1][bucket] for bucket in ("local", "other"))
    completed_age11 = sum(age11["completed"][bucket] for bucket in ("local", "other"))
    completed_11_14 = sum(
        metrics[age]["completed"][bucket]
        for age in range(11, 15)
        for bucket in ("local", "other")
    )
    ppc_11_14 = sum(metrics[age]["ppc"] for age in range(11, 15))

    ws["F40"] = grade1_age6
    ws["G40"] = _th_m1_percent(grade1_age6, age6["ppc"])
    ws["F41"] = completed_age11
    ws["G41"] = _th_m1_percent(completed_age11, age11["ppc"])
    ws["F42"] = primary_age11
    ws["G42"] = _th_m1_percent(primary_age11, age11["ppc"])
    ws["F43"] = completed_11_14
    ws["G43"] = _th_m1_percent(completed_11_14, ppc_11_14)
    ws["F44"] = None
    ws["G44"] = None

    # Không giữ tên người lập/ký của tệp địa phương mẫu.
    for cell_ref in ("D52", "J52"):
        ws[cell_ref] = None

    output = BytesIO()
    workbook.save(output)
    output.seek(0)

    safe_scope = _th_m1_norm(scope_title).replace(" ", "_") or "TOAN_TINH"
    year_code = str(school_year.code or reference_year).replace("/", "-")
    filename = f"PCGD_TH_M1_{year_code}_{safe_scope}.xlsx"
    return output, filename


def _export_primary_th_m1(
    *,
    db: Session,
    request: Request,
    school_year: SchoolYear | None,
    selected_commune_id: int | None,
    selected_school_id: int | None,
    scope_label: str,
) -> StreamingResponse:
    output, filename = _build_primary_th_m1_workbook(
        db=db,
        request=request,
        school_year=school_year,
        selected_commune_id=selected_commune_id,
        selected_school_id=selected_school_id,
        scope_label=scope_label,
    )
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
# === BAI_13C_1_TH_M1_END ===
'''


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_with_parent(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def collect_route_signatures(text: str) -> list[str]:
    # So sánh chính các decorator route; không yêu cầu import app.
    signatures = re.findall(
        r"@router\.(get|post|put|delete|patch)\(\s*([\"\'][^\"\']*[\"\'])",
        text,
    )
    return [f"{method}:{path}" for method, path in signatures]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Khong tim thay vi tri can sua: {label}")
    return text.replace(old, new, 1)


def remove_existing_marker(text: str) -> str:
    pattern = re.compile(
        re.escape(MARKER_START) + r".*?" + re.escape(MARKER_END) + r"\n?",
        re.S,
    )
    return pattern.sub("", text)


def main() -> int:
    project = PROJECT if len(sys.argv) < 2 else Path(sys.argv[1]).expanduser().resolve()
    router_path = project / ROUTER_REL
    html_path = project / TEMPLATE_HTML_REL
    main_path = project / MAIN_REL
    db_path = project / DB_REL
    template_path = project / TEMPLATE_REL

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = project / "exports" / f"backup_bai_13c_1_th_m1_v1_{stamp}"
    backup.mkdir(parents=True, exist_ok=False)

    changed = [ROUTER_REL, TEMPLATE_HTML_REL, TEMPLATE_REL]
    created: list[str] = []

    print("\n" + "=" * 78)
    print("BAI 13C-1 - TU DONG BIEU TIEU HOC TH-M1 - V1")
    print("=" * 78)

    try:
        for required in (router_path, html_path, main_path, db_path):
            if not required.exists():
                raise FileNotFoundError(f"Khong tim thay: {required}")

        print("\nBUOC 1 - SAO LUU AN TOAN")
        for rel in changed:
            source = project / rel
            if source.exists():
                copy_with_parent(source, backup / rel)
            else:
                created.append(rel.as_posix())
        manifest = {
            "version": VERSION,
            "changed_files": [rel.as_posix() for rel in changed],
            "created_files": created,
        }
        (backup / "BAI_13C_1_MANIFEST.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8-sig",
        )
        latest = project / "exports" / "bai_13c_1_th_m1_backup_moi_nhat.txt"
        latest.write_text(str(backup), encoding="utf-8-sig")
        print("Ban sao an toan:", backup)

        main_hash_before = sha256(main_path)
        db_hash_before = sha256(db_path)
        old_router_text = router_path.read_text(encoding="utf-8-sig")
        old_route_signatures = collect_route_signatures(old_router_text)

        print("\nBUOC 2 - LUU MAU TH-M1 XLSX NGUYEN TRANG")
        template_path.parent.mkdir(parents=True, exist_ok=True)
        template_path.write_bytes(base64.b64decode(TEMPLATE_B64))
        print("Da luu:", TEMPLATE_REL.as_posix())

        print("\nBUOC 3 - BO SUNG LOGIC TU DONG TH-M1 TREN ROUTE XUAT EXCEL HIEN CO")
        text = old_router_text
        text = remove_existing_marker(text)
        text = replace_once(text, "from datetime import datetime", "from datetime import datetime\nimport re\nimport unicodedata", "import re/unicodedata")
        text = replace_once(text, "from openpyxl import Workbook", "from openpyxl import Workbook, load_workbook", "load_workbook")

        old_meta = '''    "PCGD_TH_M1_2025": {\n        "title": "TH-M1 – Báo cáo phổ cập giáo dục Tiểu học",\n        "short_title": "Tiểu học – TH-M1",\n        "description": "Biểu TH-M1 năm 2025. Đã tiếp nhận mẫu Excel gốc; bước hiện tại chỉ đăng ký danh mục, chưa tự động điền dữ liệu.",\n        "icon": "📘",\n        "stage": "Đã tiếp nhận mẫu gốc",\n        "stage_class": "next",\n        "lesson": "PCGD & XMC V1.5",\n    },'''
        new_meta = '''    "PCGD_TH_M1_2025": {\n        "title": "TH-M1 – Báo cáo phổ cập giáo dục Tiểu học",\n        "short_title": "Tiểu học – TH-M1",\n        "description": "Tự động tổng hợp từ dữ liệu điều tra 6–14 tuổi vào đúng mẫu Excel TH-M1. Hai chỉ tiêu chưa có trường dữ liệu trực tiếp (Có khả năng HT, Lưu ban) được để trống, không suy diễn.",\n        "icon": "📘",\n        "stage": "Sẵn sàng tự động",\n        "stage_class": "ready",\n        "lesson": "Bài 13C-1",\n    },'''
        if old_meta in text:
            text = text.replace(old_meta, new_meta, 1)
        elif '"PCGD_TH_M1_2025"' not in text:
            raise RuntimeError("Chua co danh muc PCGD_TH_M1_2025 cua V1.5.")

        anchor = '@router.get("/xuat-danh-muc-excel")'
        if anchor not in text:
            raise RuntimeError("Khong tim thay route xuat-danh-muc-excel hien co.")
        text = text.replace(anchor, HELPER_BLOCK + "\n\n" + anchor, 1)

        branch_anchor = '''    rows, summary = _build_report_rows(\n        db,\n        request,\n        selected_year_id,\n        selected_commune_id,\n        selected_school_id,\n        normalized_report_type,\n        normalized_status,\n        q,\n    )\n'''
        branch = '''    if normalized_report_type == "PCGD_TH_M1_2025":\n        return _export_primary_th_m1(\n            db=db,\n            request=request,\n            school_year=selected_year,\n            selected_commune_id=selected_commune_id,\n            selected_school_id=selected_school_id,\n            scope_label=scope_label,\n        )\n\n''' + branch_anchor
        text = replace_once(text, branch_anchor, branch, "nhanh xuat TH-M1")
        router_path.write_text(text, encoding="utf-8")

        print("\nBUOC 4 - DOI NHAN NUT XUAT CHO RIENG TH-M1")
        html = html_path.read_text(encoding="utf-8-sig")
        old_button = '<a class="button button-success" href="{{ export_url }}">📊 Xuất danh mục Excel</a>'
        new_button = '''{% if report_type == 'PCGD_TH_M1_2025' %}\n                <a class="button button-success" href="{{ export_url }}">📘 Xuất biểu TH-M1 Excel</a>\n                {% else %}\n                <a class="button button-success" href="{{ export_url }}">📊 Xuất danh mục Excel</a>\n                {% endif %}'''
        if old_button in html:
            html = html.replace(old_button, new_button, 1)
        elif "Xuất biểu TH-M1 Excel" not in html:
            raise RuntimeError("Khong tim thay nut Xuat danh muc Excel de gan nhan TH-M1.")
        html_path.write_text(html, encoding="utf-8")

        print("\nBUOC 5 - KIEM TRA AN TOAN")
        subprocess.run(
            [sys.executable, "-m", "py_compile", str(router_path)],
            cwd=project,
            check=True,
        )
        from jinja2 import Environment
        Environment().parse(html_path.read_text(encoding="utf-8-sig"))
        if not zipfile.is_zipfile(template_path):
            raise AssertionError("Mau TH-M1 xlsx khong phai tep XLSX hop le.")
        new_router_text = router_path.read_text(encoding="utf-8-sig")
        new_route_signatures = collect_route_signatures(new_router_text)
        if old_route_signatures != new_route_signatures:
            raise AssertionError("Danh sach route da thay doi - tu dong khoi phuc.")
        if sha256(main_path) != main_hash_before:
            raise AssertionError("app/main.py bi thay doi - tu dong khoi phuc.")
        if sha256(db_path) != db_hash_before:
            raise AssertionError("data/phocap.db bi thay doi - tu dong khoi phuc.")
        if not template_path.exists() or template_path.stat().st_size < 10000:
            raise AssertionError("Mau TH-M1 xlsx khong hop le.")

        print("Route cu: KHONG DOI")
        print("app/main.py: KHONG DOI")
        print("data/phocap.db: KHONG DOI")
        print("Chuc nang cu: GIU NGUYEN")
        print("TH-M1: DA TU DONG CAC CHI TIEU CO NGUON DU LIEU RO")
        print("Co kha nang HT: DE TRONG - CHUA CO TRUONG DU LIEU")
        print("Luu ban: DE TRONG - CHUA CO TRUONG DU LIEU")
        print("\n" + "=" * 78)
        print("CAI DAT BAI 13C-1 TH-M1 V1 THANH CONG")
        print("=" * 78)
        print("Ban sao an toan:", backup)
        return 0

    except Exception as exc:
        print("\nCAI DAT KHONG THANH CONG:")
        print(exc)
        traceback.print_exc()
        print("\nDANG KHOI PHUC...")
        for rel in reversed(changed):
            current = project / rel
            saved = backup / rel
            if saved.exists():
                copy_with_parent(saved, current)
            elif rel.as_posix() in created and current.exists():
                current.unlink()
        print("DA KHOI PHUC TRANG THAI TRUOC BAI 13C-1.")
        print("Ban sao an toan:", backup)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
