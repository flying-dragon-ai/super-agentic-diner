# UI Events Benchmark Baseline

## Scope

- skill: csharp-cs-to-java-hbsk
- mode: ui-events
- comparison: skill evidence mode vs traditional rg direct scan
- csharp-root: D:/codingProjects/#Net_副本/Source/BizModule
- pages: import-info-check, export-empty-pass, vessel-to-vessel-manage
- input modes: designer-location, codebehind-location, class-entry
- repeats: 2 per page/input mode
- rg baseline: Designer event subscriptions + handler body direct `ServiceManager<T>.Service.Method` only; no helper/callback/PerformClick/CodeGraph/downstream tracing

## Six-Dimension Baseline

| dimension | skill baseline | rg baseline | skill pass floor |
|---|---:|---:|---:|
| event coverage accuracy | 1.0000 | 1.0000 | 1.0000 |
| handler anchor accuracy | 1.0000 | 1.0000 | 1.0000 |
| interface call recall | 1.0000 | 0.2096 | >= 0.9500 |
| indirect chain recall | 1.0000 | 0.0000 | >= 0.9000 |
| downstream evidence recall | 1.0000 | 0.0000 | >= 0.8000 |
| repeat stability | 1.0000 | 1.0000 | 1.0000 |

## Runtime Baseline

| strategy | total runs | failed runs | success rate | avg seconds | max seconds |
|---|---:|---:|---:|---:|---:|
| rg | 18 | 0 | 1.0000 | 1.482 | 6.674 |
| skill | 18 | 0 | 1.0000 | 19.233 | 24.279 |

- raw rg is 13.0x faster by wall-clock because it does not trace helpers, callbacks, Contract/BLL, or DAL/SQL evidence.
- skill efficiency is measured by evidence completeness: rg leaves helper-chain and downstream evidence work for manual follow-up.

## Case Results

| strategy | page | input | run | time(s) | events | active | no-active | method | chain | downstream | quality |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| skill | import-info-check | designer-location | 1 | 23.059 | 18 | 13 | 5 | 1.000 | 1.000 | 1.000 | pass |
| skill | import-info-check | designer-location | 2 | 18.876 | 18 | 13 | 5 | 1.000 | 1.000 | 1.000 | pass |
| skill | import-info-check | codebehind-location | 1 | 16.832 | 18 | 13 | 5 | 1.000 | 1.000 | 1.000 | pass |
| skill | import-info-check | codebehind-location | 2 | 19.505 | 18 | 13 | 5 | 1.000 | 1.000 | 1.000 | pass |
| skill | import-info-check | class-entry | 1 | 18.446 | 18 | 13 | 5 | 1.000 | 1.000 | 1.000 | pass |
| skill | import-info-check | class-entry | 2 | 20.943 | 18 | 13 | 5 | 1.000 | 1.000 | 1.000 | pass |
| skill | export-empty-pass | designer-location | 1 | 24.279 | 21 | 6 | 15 | 1.000 | 1.000 | 1.000 | pass |
| skill | export-empty-pass | designer-location | 2 | 23.363 | 21 | 6 | 15 | 1.000 | 1.000 | 1.000 | pass |
| skill | export-empty-pass | codebehind-location | 1 | 19.019 | 21 | 6 | 15 | 1.000 | 1.000 | 1.000 | pass |
| skill | export-empty-pass | codebehind-location | 2 | 21.036 | 21 | 6 | 15 | 1.000 | 1.000 | 1.000 | pass |
| skill | export-empty-pass | class-entry | 1 | 22.564 | 21 | 6 | 15 | 1.000 | 1.000 | 1.000 | pass |
| skill | export-empty-pass | class-entry | 2 | 23.782 | 21 | 6 | 15 | 1.000 | 1.000 | 1.000 | pass |
| skill | vessel-to-vessel-manage | designer-location | 1 | 15.227 | 25 | 6 | 19 | 1.000 | 1.000 | 1.000 | pass |
| skill | vessel-to-vessel-manage | designer-location | 2 | 15.609 | 25 | 6 | 19 | 1.000 | 1.000 | 1.000 | pass |
| skill | vessel-to-vessel-manage | codebehind-location | 1 | 15.827 | 25 | 6 | 19 | 1.000 | 1.000 | 1.000 | pass |
| skill | vessel-to-vessel-manage | codebehind-location | 2 | 15.788 | 25 | 6 | 19 | 1.000 | 1.000 | 1.000 | pass |
| skill | vessel-to-vessel-manage | class-entry | 1 | 16.961 | 25 | 6 | 19 | 1.000 | 1.000 | 1.000 | pass |
| skill | vessel-to-vessel-manage | class-entry | 2 | 15.069 | 25 | 6 | 19 | 1.000 | 1.000 | 1.000 | pass |
| rg | import-info-check | designer-location | 1 | 0.029 | 18 | 5 | 13 | 0.545 | 0.000 | 0.000 | reference |
| rg | import-info-check | designer-location | 2 | 0.030 | 18 | 5 | 13 | 0.545 | 0.000 | 0.000 | reference |
| rg | import-info-check | codebehind-location | 1 | 0.031 | 18 | 5 | 13 | 0.545 | 0.000 | 0.000 | reference |
| rg | import-info-check | codebehind-location | 2 | 0.027 | 18 | 5 | 13 | 0.545 | 0.000 | 0.000 | reference |
| rg | import-info-check | class-entry | 1 | 5.855 | 18 | 5 | 13 | 0.545 | 0.000 | 0.000 | reference |
| rg | import-info-check | class-entry | 2 | 6.674 | 18 | 5 | 13 | 0.545 | 0.000 | 0.000 | reference |
| rg | export-empty-pass | designer-location | 1 | 0.035 | 21 | 1 | 20 | 0.083 | 0.000 | 0.000 | reference |
| rg | export-empty-pass | designer-location | 2 | 0.033 | 21 | 1 | 20 | 0.083 | 0.000 | 0.000 | reference |
| rg | export-empty-pass | codebehind-location | 1 | 0.031 | 21 | 1 | 20 | 0.083 | 0.000 | 0.000 | reference |
| rg | export-empty-pass | codebehind-location | 2 | 0.034 | 21 | 1 | 20 | 0.083 | 0.000 | 0.000 | reference |
| rg | export-empty-pass | class-entry | 1 | 3.224 | 21 | 1 | 20 | 0.083 | 0.000 | 0.000 | reference |
| rg | export-empty-pass | class-entry | 2 | 2.353 | 21 | 1 | 20 | 0.083 | 0.000 | 0.000 | reference |
| rg | vessel-to-vessel-manage | designer-location | 1 | 0.035 | 25 | 0 | 25 | 0.000 | 0.000 | 0.000 | reference |
| rg | vessel-to-vessel-manage | designer-location | 2 | 0.036 | 25 | 0 | 25 | 0.000 | 0.000 | 0.000 | reference |
| rg | vessel-to-vessel-manage | codebehind-location | 1 | 0.035 | 25 | 0 | 25 | 0.000 | 0.000 | 0.000 | reference |
| rg | vessel-to-vessel-manage | codebehind-location | 2 | 0.032 | 25 | 0 | 25 | 0.000 | 0.000 | 0.000 | reference |
| rg | vessel-to-vessel-manage | class-entry | 1 | 3.163 | 25 | 0 | 25 | 0.000 | 0.000 | 0.000 | reference |
| rg | vessel-to-vessel-manage | class-entry | 2 | 5.010 | 25 | 0 | 25 | 0.000 | 0.000 | 0.000 | reference |

## Misses

- rg / import-info-check / designer-location / run 1: method_misses=['IVoyageCheckLog.GetVoyageCheckLogs', 'IVoyageCheckLog.CheckInBoundCntrsLocation', 'IVoyageCheckLog.GetAccordPropsRules', 'IVoyageCheckLog.HandleAccordPropsRules', 'IGeneralService.GetRefCodeByDomainCode']; chain_misses=['bbiFind_ItemClick -> BindCheckLogs', 'bbiRefresh_ItemClick -> GridRefresh -> BindCheckLogs', 'bbiImport_ItemClick -> PropCheckRuleForm_Closing -> SavePropCheckRules', 'gcVoyage_MouseDoubleClick -> bbiShowDetail_ItemClick', 'ImportInfoCheckMainForm_Load -> isCoperCheck']; downstream_misses=['IVoyageCheckLog.GetVoyageCheckLogs', 'IVoyageCheckLog.SaveVoyageCheckLog', 'IVoyageCheckLog.GetCheckResults', 'IVoyageService.GetImportVoyageBy', 'IGeneralService.GetRefCodeByDomainCode']
- rg / import-info-check / designer-location / run 2: method_misses=['IVoyageCheckLog.GetVoyageCheckLogs', 'IVoyageCheckLog.CheckInBoundCntrsLocation', 'IVoyageCheckLog.GetAccordPropsRules', 'IVoyageCheckLog.HandleAccordPropsRules', 'IGeneralService.GetRefCodeByDomainCode']; chain_misses=['bbiFind_ItemClick -> BindCheckLogs', 'bbiRefresh_ItemClick -> GridRefresh -> BindCheckLogs', 'bbiImport_ItemClick -> PropCheckRuleForm_Closing -> SavePropCheckRules', 'gcVoyage_MouseDoubleClick -> bbiShowDetail_ItemClick', 'ImportInfoCheckMainForm_Load -> isCoperCheck']; downstream_misses=['IVoyageCheckLog.GetVoyageCheckLogs', 'IVoyageCheckLog.SaveVoyageCheckLog', 'IVoyageCheckLog.GetCheckResults', 'IVoyageService.GetImportVoyageBy', 'IGeneralService.GetRefCodeByDomainCode']
- rg / import-info-check / codebehind-location / run 1: method_misses=['IVoyageCheckLog.GetVoyageCheckLogs', 'IVoyageCheckLog.CheckInBoundCntrsLocation', 'IVoyageCheckLog.GetAccordPropsRules', 'IVoyageCheckLog.HandleAccordPropsRules', 'IGeneralService.GetRefCodeByDomainCode']; chain_misses=['bbiFind_ItemClick -> BindCheckLogs', 'bbiRefresh_ItemClick -> GridRefresh -> BindCheckLogs', 'bbiImport_ItemClick -> PropCheckRuleForm_Closing -> SavePropCheckRules', 'gcVoyage_MouseDoubleClick -> bbiShowDetail_ItemClick', 'ImportInfoCheckMainForm_Load -> isCoperCheck']; downstream_misses=['IVoyageCheckLog.GetVoyageCheckLogs', 'IVoyageCheckLog.SaveVoyageCheckLog', 'IVoyageCheckLog.GetCheckResults', 'IVoyageService.GetImportVoyageBy', 'IGeneralService.GetRefCodeByDomainCode']
- rg / import-info-check / codebehind-location / run 2: method_misses=['IVoyageCheckLog.GetVoyageCheckLogs', 'IVoyageCheckLog.CheckInBoundCntrsLocation', 'IVoyageCheckLog.GetAccordPropsRules', 'IVoyageCheckLog.HandleAccordPropsRules', 'IGeneralService.GetRefCodeByDomainCode']; chain_misses=['bbiFind_ItemClick -> BindCheckLogs', 'bbiRefresh_ItemClick -> GridRefresh -> BindCheckLogs', 'bbiImport_ItemClick -> PropCheckRuleForm_Closing -> SavePropCheckRules', 'gcVoyage_MouseDoubleClick -> bbiShowDetail_ItemClick', 'ImportInfoCheckMainForm_Load -> isCoperCheck']; downstream_misses=['IVoyageCheckLog.GetVoyageCheckLogs', 'IVoyageCheckLog.SaveVoyageCheckLog', 'IVoyageCheckLog.GetCheckResults', 'IVoyageService.GetImportVoyageBy', 'IGeneralService.GetRefCodeByDomainCode']
- rg / import-info-check / class-entry / run 1: method_misses=['IVoyageCheckLog.GetVoyageCheckLogs', 'IVoyageCheckLog.CheckInBoundCntrsLocation', 'IVoyageCheckLog.GetAccordPropsRules', 'IVoyageCheckLog.HandleAccordPropsRules', 'IGeneralService.GetRefCodeByDomainCode']; chain_misses=['bbiFind_ItemClick -> BindCheckLogs', 'bbiRefresh_ItemClick -> GridRefresh -> BindCheckLogs', 'bbiImport_ItemClick -> PropCheckRuleForm_Closing -> SavePropCheckRules', 'gcVoyage_MouseDoubleClick -> bbiShowDetail_ItemClick', 'ImportInfoCheckMainForm_Load -> isCoperCheck']; downstream_misses=['IVoyageCheckLog.GetVoyageCheckLogs', 'IVoyageCheckLog.SaveVoyageCheckLog', 'IVoyageCheckLog.GetCheckResults', 'IVoyageService.GetImportVoyageBy', 'IGeneralService.GetRefCodeByDomainCode']
- rg / import-info-check / class-entry / run 2: method_misses=['IVoyageCheckLog.GetVoyageCheckLogs', 'IVoyageCheckLog.CheckInBoundCntrsLocation', 'IVoyageCheckLog.GetAccordPropsRules', 'IVoyageCheckLog.HandleAccordPropsRules', 'IGeneralService.GetRefCodeByDomainCode']; chain_misses=['bbiFind_ItemClick -> BindCheckLogs', 'bbiRefresh_ItemClick -> GridRefresh -> BindCheckLogs', 'bbiImport_ItemClick -> PropCheckRuleForm_Closing -> SavePropCheckRules', 'gcVoyage_MouseDoubleClick -> bbiShowDetail_ItemClick', 'ImportInfoCheckMainForm_Load -> isCoperCheck']; downstream_misses=['IVoyageCheckLog.GetVoyageCheckLogs', 'IVoyageCheckLog.SaveVoyageCheckLog', 'IVoyageCheckLog.GetCheckResults', 'IVoyageService.GetImportVoyageBy', 'IGeneralService.GetRefCodeByDomainCode']
- rg / export-empty-pass / designer-location / run 1: method_misses=['IExportEmptyPass.GetEmptyLoadPlans', 'IExportEmptyPass.GetEmptyLoadUseCRs', 'IExportEmptyPass.GetEmptyLoadContainers', 'IPortOfCalling.GetPortOfCallings', 'IVoyageService.GetVoyageView', 'IExportEmptyPass.SetEmptyContainerPass', 'IExportEmptyPass.ReleaseEmptyContainerPass', 'IExportEmptyPass.SetContainerBillNo', 'IExportEmptyPass.SendCostrps', 'IVoyageClose.VoyageIsShut', 'IGeneralService.GetAllCustomer']; chain_misses=['bbiFind_ItemClick -> LoadSearchDialog -> LoadData -> GetEmptyLoadPlanList', 'bbiSave_ItemClick -> SaveContainerPass', 'btnSetBillNo_Click -> SetBillNo -> IVoyageClose.VoyageIsShut', 'btnSetBillNo_Click -> bbiSendCostrp_ItemClick -> SendCostrp', 'ExportEmptyPassMainForm_Load -> BindCustomerName']; downstream_misses=['IExportEmptyPass.GetEmptyLoadPlans', 'IExportEmptyPass.SetContainerBillNo', 'IExportEmptyPass.SendCostrps', 'IExportEmptyPass.IsNotAllowEmptyPass', 'IVoyageClose.VoyageIsShut']
- rg / export-empty-pass / designer-location / run 2: method_misses=['IExportEmptyPass.GetEmptyLoadPlans', 'IExportEmptyPass.GetEmptyLoadUseCRs', 'IExportEmptyPass.GetEmptyLoadContainers', 'IPortOfCalling.GetPortOfCallings', 'IVoyageService.GetVoyageView', 'IExportEmptyPass.SetEmptyContainerPass', 'IExportEmptyPass.ReleaseEmptyContainerPass', 'IExportEmptyPass.SetContainerBillNo', 'IExportEmptyPass.SendCostrps', 'IVoyageClose.VoyageIsShut', 'IGeneralService.GetAllCustomer']; chain_misses=['bbiFind_ItemClick -> LoadSearchDialog -> LoadData -> GetEmptyLoadPlanList', 'bbiSave_ItemClick -> SaveContainerPass', 'btnSetBillNo_Click -> SetBillNo -> IVoyageClose.VoyageIsShut', 'btnSetBillNo_Click -> bbiSendCostrp_ItemClick -> SendCostrp', 'ExportEmptyPassMainForm_Load -> BindCustomerName']; downstream_misses=['IExportEmptyPass.GetEmptyLoadPlans', 'IExportEmptyPass.SetContainerBillNo', 'IExportEmptyPass.SendCostrps', 'IExportEmptyPass.IsNotAllowEmptyPass', 'IVoyageClose.VoyageIsShut']
- rg / export-empty-pass / codebehind-location / run 1: method_misses=['IExportEmptyPass.GetEmptyLoadPlans', 'IExportEmptyPass.GetEmptyLoadUseCRs', 'IExportEmptyPass.GetEmptyLoadContainers', 'IPortOfCalling.GetPortOfCallings', 'IVoyageService.GetVoyageView', 'IExportEmptyPass.SetEmptyContainerPass', 'IExportEmptyPass.ReleaseEmptyContainerPass', 'IExportEmptyPass.SetContainerBillNo', 'IExportEmptyPass.SendCostrps', 'IVoyageClose.VoyageIsShut', 'IGeneralService.GetAllCustomer']; chain_misses=['bbiFind_ItemClick -> LoadSearchDialog -> LoadData -> GetEmptyLoadPlanList', 'bbiSave_ItemClick -> SaveContainerPass', 'btnSetBillNo_Click -> SetBillNo -> IVoyageClose.VoyageIsShut', 'btnSetBillNo_Click -> bbiSendCostrp_ItemClick -> SendCostrp', 'ExportEmptyPassMainForm_Load -> BindCustomerName']; downstream_misses=['IExportEmptyPass.GetEmptyLoadPlans', 'IExportEmptyPass.SetContainerBillNo', 'IExportEmptyPass.SendCostrps', 'IExportEmptyPass.IsNotAllowEmptyPass', 'IVoyageClose.VoyageIsShut']
- rg / export-empty-pass / codebehind-location / run 2: method_misses=['IExportEmptyPass.GetEmptyLoadPlans', 'IExportEmptyPass.GetEmptyLoadUseCRs', 'IExportEmptyPass.GetEmptyLoadContainers', 'IPortOfCalling.GetPortOfCallings', 'IVoyageService.GetVoyageView', 'IExportEmptyPass.SetEmptyContainerPass', 'IExportEmptyPass.ReleaseEmptyContainerPass', 'IExportEmptyPass.SetContainerBillNo', 'IExportEmptyPass.SendCostrps', 'IVoyageClose.VoyageIsShut', 'IGeneralService.GetAllCustomer']; chain_misses=['bbiFind_ItemClick -> LoadSearchDialog -> LoadData -> GetEmptyLoadPlanList', 'bbiSave_ItemClick -> SaveContainerPass', 'btnSetBillNo_Click -> SetBillNo -> IVoyageClose.VoyageIsShut', 'btnSetBillNo_Click -> bbiSendCostrp_ItemClick -> SendCostrp', 'ExportEmptyPassMainForm_Load -> BindCustomerName']; downstream_misses=['IExportEmptyPass.GetEmptyLoadPlans', 'IExportEmptyPass.SetContainerBillNo', 'IExportEmptyPass.SendCostrps', 'IExportEmptyPass.IsNotAllowEmptyPass', 'IVoyageClose.VoyageIsShut']
- rg / export-empty-pass / class-entry / run 1: method_misses=['IExportEmptyPass.GetEmptyLoadPlans', 'IExportEmptyPass.GetEmptyLoadUseCRs', 'IExportEmptyPass.GetEmptyLoadContainers', 'IPortOfCalling.GetPortOfCallings', 'IVoyageService.GetVoyageView', 'IExportEmptyPass.SetEmptyContainerPass', 'IExportEmptyPass.ReleaseEmptyContainerPass', 'IExportEmptyPass.SetContainerBillNo', 'IExportEmptyPass.SendCostrps', 'IVoyageClose.VoyageIsShut', 'IGeneralService.GetAllCustomer']; chain_misses=['bbiFind_ItemClick -> LoadSearchDialog -> LoadData -> GetEmptyLoadPlanList', 'bbiSave_ItemClick -> SaveContainerPass', 'btnSetBillNo_Click -> SetBillNo -> IVoyageClose.VoyageIsShut', 'btnSetBillNo_Click -> bbiSendCostrp_ItemClick -> SendCostrp', 'ExportEmptyPassMainForm_Load -> BindCustomerName']; downstream_misses=['IExportEmptyPass.GetEmptyLoadPlans', 'IExportEmptyPass.SetContainerBillNo', 'IExportEmptyPass.SendCostrps', 'IExportEmptyPass.IsNotAllowEmptyPass', 'IVoyageClose.VoyageIsShut']
- rg / export-empty-pass / class-entry / run 2: method_misses=['IExportEmptyPass.GetEmptyLoadPlans', 'IExportEmptyPass.GetEmptyLoadUseCRs', 'IExportEmptyPass.GetEmptyLoadContainers', 'IPortOfCalling.GetPortOfCallings', 'IVoyageService.GetVoyageView', 'IExportEmptyPass.SetEmptyContainerPass', 'IExportEmptyPass.ReleaseEmptyContainerPass', 'IExportEmptyPass.SetContainerBillNo', 'IExportEmptyPass.SendCostrps', 'IVoyageClose.VoyageIsShut', 'IGeneralService.GetAllCustomer']; chain_misses=['bbiFind_ItemClick -> LoadSearchDialog -> LoadData -> GetEmptyLoadPlanList', 'bbiSave_ItemClick -> SaveContainerPass', 'btnSetBillNo_Click -> SetBillNo -> IVoyageClose.VoyageIsShut', 'btnSetBillNo_Click -> bbiSendCostrp_ItemClick -> SendCostrp', 'ExportEmptyPassMainForm_Load -> BindCustomerName']; downstream_misses=['IExportEmptyPass.GetEmptyLoadPlans', 'IExportEmptyPass.SetContainerBillNo', 'IExportEmptyPass.SendCostrps', 'IExportEmptyPass.IsNotAllowEmptyPass', 'IVoyageClose.VoyageIsShut']
- rg / vessel-to-vessel-manage / designer-location / run 1: method_misses=['IVesselToVessel.GetTransferContainerListBy', 'IVesselToVessel.SaveVesselToVessel', 'IPortOfCalling.GetRelatePorts', 'IRefCode.GetRefCodes', 'IVoyageService.GetExportVoyageList', 'IVoyageService.GetImportVoyageList', 'IGeneralService.GetAllCustomer', 'IGeneralService.GetRefCodeByDomainCode']; chain_misses=['bbiFind_ItemClick -> ShowSearchDialog -> LoadData', 'bbiSave_ItemClick -> SaveVslToVsl', 'lueVVVslName_EditValueChanging -> LoadPOCPorts', 'VesselToVesselManageForm_Load -> LoadBaseData -> LoadVoyage', 'VesselToVesselManageForm_Load -> LoadBaseData -> SetAdditionalOperateBinding']; downstream_misses=['IVesselToVessel.GetTransferContainerListBy', 'IVesselToVessel.SaveVesselToVessel', 'IPortOfCalling.GetRelatePorts', 'IVoyageService.GetExportVoyageList', 'IRefCode.GetRefCodes']
- rg / vessel-to-vessel-manage / designer-location / run 2: method_misses=['IVesselToVessel.GetTransferContainerListBy', 'IVesselToVessel.SaveVesselToVessel', 'IPortOfCalling.GetRelatePorts', 'IRefCode.GetRefCodes', 'IVoyageService.GetExportVoyageList', 'IVoyageService.GetImportVoyageList', 'IGeneralService.GetAllCustomer', 'IGeneralService.GetRefCodeByDomainCode']; chain_misses=['bbiFind_ItemClick -> ShowSearchDialog -> LoadData', 'bbiSave_ItemClick -> SaveVslToVsl', 'lueVVVslName_EditValueChanging -> LoadPOCPorts', 'VesselToVesselManageForm_Load -> LoadBaseData -> LoadVoyage', 'VesselToVesselManageForm_Load -> LoadBaseData -> SetAdditionalOperateBinding']; downstream_misses=['IVesselToVessel.GetTransferContainerListBy', 'IVesselToVessel.SaveVesselToVessel', 'IPortOfCalling.GetRelatePorts', 'IVoyageService.GetExportVoyageList', 'IRefCode.GetRefCodes']
- rg / vessel-to-vessel-manage / codebehind-location / run 1: method_misses=['IVesselToVessel.GetTransferContainerListBy', 'IVesselToVessel.SaveVesselToVessel', 'IPortOfCalling.GetRelatePorts', 'IRefCode.GetRefCodes', 'IVoyageService.GetExportVoyageList', 'IVoyageService.GetImportVoyageList', 'IGeneralService.GetAllCustomer', 'IGeneralService.GetRefCodeByDomainCode']; chain_misses=['bbiFind_ItemClick -> ShowSearchDialog -> LoadData', 'bbiSave_ItemClick -> SaveVslToVsl', 'lueVVVslName_EditValueChanging -> LoadPOCPorts', 'VesselToVesselManageForm_Load -> LoadBaseData -> LoadVoyage', 'VesselToVesselManageForm_Load -> LoadBaseData -> SetAdditionalOperateBinding']; downstream_misses=['IVesselToVessel.GetTransferContainerListBy', 'IVesselToVessel.SaveVesselToVessel', 'IPortOfCalling.GetRelatePorts', 'IVoyageService.GetExportVoyageList', 'IRefCode.GetRefCodes']
- rg / vessel-to-vessel-manage / codebehind-location / run 2: method_misses=['IVesselToVessel.GetTransferContainerListBy', 'IVesselToVessel.SaveVesselToVessel', 'IPortOfCalling.GetRelatePorts', 'IRefCode.GetRefCodes', 'IVoyageService.GetExportVoyageList', 'IVoyageService.GetImportVoyageList', 'IGeneralService.GetAllCustomer', 'IGeneralService.GetRefCodeByDomainCode']; chain_misses=['bbiFind_ItemClick -> ShowSearchDialog -> LoadData', 'bbiSave_ItemClick -> SaveVslToVsl', 'lueVVVslName_EditValueChanging -> LoadPOCPorts', 'VesselToVesselManageForm_Load -> LoadBaseData -> LoadVoyage', 'VesselToVesselManageForm_Load -> LoadBaseData -> SetAdditionalOperateBinding']; downstream_misses=['IVesselToVessel.GetTransferContainerListBy', 'IVesselToVessel.SaveVesselToVessel', 'IPortOfCalling.GetRelatePorts', 'IVoyageService.GetExportVoyageList', 'IRefCode.GetRefCodes']
- rg / vessel-to-vessel-manage / class-entry / run 1: method_misses=['IVesselToVessel.GetTransferContainerListBy', 'IVesselToVessel.SaveVesselToVessel', 'IPortOfCalling.GetRelatePorts', 'IRefCode.GetRefCodes', 'IVoyageService.GetExportVoyageList', 'IVoyageService.GetImportVoyageList', 'IGeneralService.GetAllCustomer', 'IGeneralService.GetRefCodeByDomainCode']; chain_misses=['bbiFind_ItemClick -> ShowSearchDialog -> LoadData', 'bbiSave_ItemClick -> SaveVslToVsl', 'lueVVVslName_EditValueChanging -> LoadPOCPorts', 'VesselToVesselManageForm_Load -> LoadBaseData -> LoadVoyage', 'VesselToVesselManageForm_Load -> LoadBaseData -> SetAdditionalOperateBinding']; downstream_misses=['IVesselToVessel.GetTransferContainerListBy', 'IVesselToVessel.SaveVesselToVessel', 'IPortOfCalling.GetRelatePorts', 'IVoyageService.GetExportVoyageList', 'IRefCode.GetRefCodes']
- rg / vessel-to-vessel-manage / class-entry / run 2: method_misses=['IVesselToVessel.GetTransferContainerListBy', 'IVesselToVessel.SaveVesselToVessel', 'IPortOfCalling.GetRelatePorts', 'IRefCode.GetRefCodes', 'IVoyageService.GetExportVoyageList', 'IVoyageService.GetImportVoyageList', 'IGeneralService.GetAllCustomer', 'IGeneralService.GetRefCodeByDomainCode']; chain_misses=['bbiFind_ItemClick -> ShowSearchDialog -> LoadData', 'bbiSave_ItemClick -> SaveVslToVsl', 'lueVVVslName_EditValueChanging -> LoadPOCPorts', 'VesselToVesselManageForm_Load -> LoadBaseData -> LoadVoyage', 'VesselToVesselManageForm_Load -> LoadBaseData -> SetAdditionalOperateBinding']; downstream_misses=['IVesselToVessel.GetTransferContainerListBy', 'IVesselToVessel.SaveVesselToVessel', 'IPortOfCalling.GetRelatePorts', 'IVoyageService.GetExportVoyageList', 'IRefCode.GetRefCodes']

## Machine-Readable Summary

```json
{
  "rg": {
    "event_summary_accuracy": 1.0,
    "handler_anchor_accuracy": 1.0,
    "interface_call_recall": 0.2096,
    "indirect_chain_recall": 0.0,
    "downstream_evidence_recall": 0.0,
    "average_elapsed_seconds": 1.482,
    "max_elapsed_seconds": 6.674,
    "success_rate": 1.0,
    "repeat_stability": 1.0,
    "total_runs": 18,
    "failed_runs": 0
  },
  "skill": {
    "event_summary_accuracy": 1.0,
    "handler_anchor_accuracy": 1.0,
    "interface_call_recall": 1.0,
    "indirect_chain_recall": 1.0,
    "downstream_evidence_recall": 1.0,
    "average_elapsed_seconds": 19.233,
    "max_elapsed_seconds": 24.279,
    "success_rate": 1.0,
    "repeat_stability": 1.0,
    "total_runs": 18,
    "failed_runs": 0
  }
}
```

## Regression Rule

Future ui-events optimizations must not reduce any skill six-dimension baseline value, must not introduce new skill per-case misses, and should keep the rg comparison for context.
