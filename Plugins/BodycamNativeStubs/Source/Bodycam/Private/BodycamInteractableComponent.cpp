#include "BodycamInteractableComponent.h"

#include "Engine/World.h"
#include "GameFramework/Actor.h"

namespace
{
	// Game Blueprints whose "On Interaction" event is bound in the game's own levels, with the bound function's name.
	// A cooked level never rebuilds these bindings, so a placed actor must carry them in the saved level.
	// Read from the game's LobbyB level (BP_MusicPlayer_C_0, component BodycamInteractable).
	struct FKnownBinding
	{
		const TCHAR* OwnerClass;
		const TCHAR* ComponentName;
		const TCHAR* FunctionName;
	};

	const FKnownBinding KnownBindings[] = {
		{ TEXT("BP_MusicPlayer_C"), TEXT("BodycamInteractable"),
		  TEXT("BndEvt__GeneratorElectrical_BodycamInteractable_K2Node_ComponentBoundEvent_0_OnInteraction__DelegateSignature") },
	};
}

void UBodycamInteractableComponent::OnRegister()
{
	Super::OnRegister();

	const UWorld* World = GetWorld();
	AActor* Owner = GetOwner();
	if (!World || !Owner || World->IsGameWorld())
	{
		return;
	}
	for (const FKnownBinding& Binding : KnownBindings)
	{
		if (Owner->GetClass()->GetName() == Binding.OwnerClass && GetName() == Binding.ComponentName)
		{
			FScriptDelegate Delegate;
			Delegate.BindUFunction(Owner, FName(Binding.FunctionName));
			OnInteraction.AddUnique(Delegate);
		}
	}
}

void UBodycamInteractableComponent::BeginPlay()
{
	Super::BeginPlay();
	// Play in Editor: the placeholder Blueprint has none of the bound functions, so nothing may be called.
	OnInteraction.Clear();
}
