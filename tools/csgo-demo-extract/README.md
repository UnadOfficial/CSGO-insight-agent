# csgo-demo-extract

Source 1 CS:GO demo extractor used by CSGO Insight Agent.

```powershell
cd tools/csgo-demo-extract
go mod tidy
go build -o csgo-demo-extract.exe .
.\csgo-demo-extract.exe --version
```

The Python backend looks for this binary next to the sources, or in
`CSGO_INSIGHT_DEMO_EXTRACT`.
