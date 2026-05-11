
Agent-Based Model of the UK Housing Market
==========================================

This is an agent-based model of the UK housing market improved by Max Stoddard at Imperial College London for his BEng Computing final-year project, in collaboration with the Bank of England. The legacy model in this project was written by the Institute of New Economic Thinking at the University of Oxford, in collaboration with the Bank of England ([GitHub](https://github.com/INET-Complexity/housing-model)). It is intended for use as a tool for informing central bank regulation policy.

The model incorporates owner-occupiers, renters, buy-to-let investors, a housing market, a rental market, banks, a central bank and a government. A more detailed description of the model can be found at this
[Bank of England Working Paper](https://www.bankofengland.co.uk/working-paper/2016/macroprudential-policy-in-an-agent-based-model-of-the-uk-housing-market) and at the
ModelDescriptionFeb16.pdf file.

Dashboard (local):

```bash
./run-dashboard.sh
```

Java model builds should use the repo-local Maven wrapper:

```bash
./mvnw -q test
```
