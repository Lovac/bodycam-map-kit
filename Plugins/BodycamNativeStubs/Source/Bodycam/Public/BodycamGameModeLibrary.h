// INSTALLED 27 Sep 2026: stand-in for the game's native /Script/Bodycam.BodycamGameModeLibrary, for
// Plugins/BodycamNativeStubs/Source/Bodycam/Public/. Editor only, never packed: the game resolves the cooked
// EX_CallMath imports to its own class by name (LinkerLoad.cpp 5759-5762).
// Signatures decoded from the game's exe reflection tables (coord_scratch/team/exe_ufunc.py):
//   AreOnSameTeam   FunctionFlags 0x14022401, params Character1 (Object, Character), Character2 (Object, Character),
//                   ReturnValue (bool, NativeBool), parms size 24
//   IsNewGameMode   0x14022401, WorldContextObject (Object), ReturnValue (bool), parms size 16
//   GetPlayerTeamID 0x14022401, PlayerState (Object, PlayerState, CPF_ConstParm), ReturnValue (int32), parms size 16
// static + BlueprintPure in a UBlueprintFunctionLibrary gives Final|Native|Static|Public|BlueprintCallable|BlueprintPure
// = 0x14022401, the same flags, so the Kismet compiler emits EX_CallMath (KismetCompilerVMBackend.cpp 1308-1346).
// Bodies are never run in the game.
#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "GameFramework/Character.h"
#include "BodycamGameModeLibrary.generated.h"

class ACharacter;
class APlayerState;

UCLASS()
class BODYCAM_API UBodycamGameModeLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintPure, Category = "Bodycam|Team")
	// Lab mock (never runs in the game, which uses its own native): both characters carry the same "team:N" actor tag.
	static bool AreOnSameTeam(ACharacter* Character1, ACharacter* Character2) { return LabTeam(Character1) >= 0 && LabTeam(Character1) == LabTeam(Character2); }

	UFUNCTION(BlueprintPure, Category = "Bodycam|Team", meta = (WorldContext = "WorldContextObject"))
	static bool IsNewGameMode(UObject* WorldContextObject) { return false; }

	UFUNCTION(BlueprintPure, Category = "Bodycam|Team")
	static int32 GetPlayerTeamID(const APlayerState* PlayerState) { return -1; }

private:
	static int32 LabTeam(const AActor* A)
	{
		if (!A) return -1;
		for (const FName& T : A->Tags)
		{
			const FString S = T.ToString();
			if (S.StartsWith(TEXT("team:"))) return FCString::Atoi(*S.Mid(5));
		}
		return -1;
	}
};
