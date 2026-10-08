// Stand-in for the game's /Script/Bodycam.BodycamInteractableComponent.
// Parent class, property names and property types match the game's usmap (Bodycam 5.5.4). No gameplay code.
#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "GameplayTagContainer.h"
#include "BodycamInteractableComponent.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FBodycamInteractionSignature, AActor*, Interactor);

UCLASS(ClassGroup = (Bodycam), meta = (BlueprintSpawnableComponent))
class BODYCAM_API UBodycamInteractableComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UPROPERTY(BlueprintAssignable, Category = "Interaction")
	FBodycamInteractionSignature OnInteraction;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interaction")
	bool bCanInteract = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interaction")
	bool bShowWidget = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interaction")
	bool bIsPickable = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interaction")
	bool bShouldExecuteOnServer = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interaction")
	bool bEnableLineOfSightCheck = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interaction")
	FGameplayTagContainer ItemSlots;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interaction")
	TObjectPtr<UObject> InteractionWidget;

	virtual void OnRegister() override;
	virtual void BeginPlay() override;
};
