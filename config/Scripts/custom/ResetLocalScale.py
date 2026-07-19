from pyfbsdk import FBModelList, FBGetSelectedModels, FBVector3d, FBMessageBox

lSelectedModels = FBModelList()
FBGetSelectedModels( lSelectedModels )

## Resets local Scale
if len(lSelectedModels)==0:
    FBMessageBox("Reset Local Scale on selected objects", "No model selected, no operation performed...", "Ok")
else:
    for lModel in lSelectedModels:
        lModel.Scaling = FBVector3d()

# Cleanup of local objects
del( lSelectedModels )

# Cleanup of imported modules
del( FBModelList, FBGetSelectedModels, FBVector3d )
