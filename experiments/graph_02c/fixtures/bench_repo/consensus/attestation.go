package consensus

// Prysm-style camelCase mirror of pyspec process_attestation
func ProcessAttestation(state *State, att *Attestation) error {
	if att == nil {
		return errNil
	}
	return nil
}

type State struct{ epoch uint64 }
