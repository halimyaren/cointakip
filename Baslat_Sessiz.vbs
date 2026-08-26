' CoinTakip - Sessiz Baslatici (pencere gostermeden calistirir)
' Yol sabit kodlanmaz; script kendi bulundugu klasoru referans alir.
' Boylece proje baska bir dizine tasinsa da calismaya devam eder.
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = scriptDir & "\app"

' Baslat.bat ile ayni komut kullanilir (main.py'nin __main__ blogu devreye girmez,
' aksi halde tarayici iki kez acilir).
WshShell.Run "python -m uvicorn main:app --host 127.0.0.1 --port 8000", 0, False
WScript.Sleep 2000
WshShell.Run "http://localhost:8000"
