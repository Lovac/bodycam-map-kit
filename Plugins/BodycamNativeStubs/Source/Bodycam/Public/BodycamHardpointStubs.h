// Stand-ins for the game's native Hardpoint classes in /Script/Bodycam.
// Parent classes, property names and property types match the game's usmap (Bodycam 5.5.4). No gameplay code.
// A cooked level never reruns construction scripts or rebinds component events, so the placed objective must be saved
// with the same components and bindings as the game's own Hardpoint levels (gate rules R1-R12).
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Components/WidgetComponent.h"
#include "HMS_Components.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "BodycamHardpointStubs.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FBodycamCountdownTickSignature, float, SecondsRemaining);
DECLARE_DYNAMIC_MULTICAST_DELEGATE(FBodycamCountdownFinishedSignature);

UCLASS(ClassGroup = (Bodycam), meta = (BlueprintSpawnableComponent))
class BODYCAM_API UCountdownComponent : public UHMS_ActorComponent
{
	GENERATED_BODY()

public:
	UPROPERTY(BlueprintAssignable, Category = "Countdown")
	FBodycamCountdownTickSignature OnTick;

	UPROPERTY(BlueprintAssignable, Category = "Countdown")
	FBodycamCountdownFinishedSignature OnFinished;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Countdown")
	float CountdownEndTime = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Countdown")
	TObjectPtr<UObject> TickSound;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Countdown")
	float HMS_SavedRemainingTime = 0.0f;
};

UCLASS(ClassGroup = (Bodycam), meta = (BlueprintSpawnableComponent))
class BODYCAM_API UBodycamWidgetComponent : public UWidgetComponent
{
	GENERATED_BODY()

public:
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Widget")
	TObjectPtr<UObject> PostProcessMaterialSettingsMPC;
};

UCLASS(Blueprintable)
class BODYCAM_API ABodycamHardPointZonePreview : public AActor
{
	GENERATED_BODY()

public:
	virtual void OnConstruction(const FTransform& Transform) override;
};

UCLASS(Blueprintable)
class BODYCAM_API ABodycamHardpointZone : public AActor
{
	GENERATED_BODY()

public:
	ABodycamHardpointZone(const FObjectInitializer& ObjectInitializer);
	virtual void OnConstruction(const FTransform& Transform) override;
	virtual void PostInitializeComponents() override;
	// Box components are rebuilt whenever the construction script reruns, so the bindings are added again right before
	// every save and cook, not only after construction.
	virtual void PreSave(FObjectPreSaveContext SaveContext) override;

	void AddEditorBindings();
	FString DescribeBindings();


	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Hardpoint")
	FName CurrentHardPointName;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Hardpoint")
	FName NextHardPointName;

	UPROPERTY(EditAnywhere, Category = "Hardpoint")
	uint32 VisitedMask = 0;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Hardpoint")
	TObjectPtr<UCountdownComponent> ZoneCountdown;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Hardpoint")
	TObjectPtr<UHMS_InterfaceComponent> HMSInterfaceComponent;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Hardpoint")
	TArray<TObjectPtr<AActor>> SortedHardPoints;
};

UCLASS()
class BODYCAM_API UBodycamStubsLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	// Lists the event bindings a Hardpoint zone will save (Python cannot read sparse delegates such as Box overlaps).
	UFUNCTION(BlueprintCallable, Category = "Bodycam")
	static FString DescribeHardpointBindings(AActor* Zone);
};
